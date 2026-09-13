"""Q3单调充电等价MILP：复用Q2验证结构，加入调整成本与正终端残值。"""
import hashlib
import time
import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from scipy.sparse import coo_matrix, hstack, vstack
from highspy import Highs as HighsAPI
from highspy import _core as highs_core
from .config import CAP, E_MIN, E_MAX, ETA, TOL, Config
from .physics import Policy, replay, adjustment
from .scenarios import Scenarios
ETA_C = ETA_D = ETA


def matrix_digest(objective, bounds, integer, constraints) -> str:
    """对完整数值矩阵建立跨后端稳定摘要；不包含求解器或热启动。"""
    matrix=constraints.A.tocsc(copy=True);matrix.sum_duplicates();matrix.sort_indices()
    digest=hashlib.sha256(b'Q3_MATRIX_CSC_V1')
    arrays=(('objective',objective,'<f8'),('bounds_lb',bounds.lb,'<f8'),('bounds_ub',bounds.ub,'<f8'),
            ('integer',integer,'<i1'),('row_lb',constraints.lb,'<f8'),('row_ub',constraints.ub,'<f8'),
            ('indptr',matrix.indptr,'<i8'),('indices',matrix.indices,'<i8'),('data',matrix.data,'<f8'))
    for name,values,dtype in arrays:
        array=np.ascontiguousarray(np.asarray(values,dtype=dtype))
        digest.update(name.encode('ascii'));digest.update(str(array.shape).encode('ascii'));digest.update(array.tobytes())
    return digest.hexdigest()


def reachable_bounds(net: np.ndarray, grid_upper: np.ndarray, initial: float) -> tuple[np.ndarray,...]:
    """仅用当前场景递推原饱和反馈的安全 SOC/充放电包络。"""
    net=np.asarray(net,dtype=float);grid_upper=np.asarray(grid_upper,dtype=float)
    s,t=net.shape
    e_lower=np.empty((s,t));e_upper=np.empty((s,t));c_upper=np.empty((s,t));r_upper=np.empty((s,t))
    for j,path in enumerate(net):
        low=high=float(initial)
        for i,n in enumerate(path):
            deficit=min(CAP,max(n,0.));surplus=min(CAP,max(float(grid_upper[i])-n,0.))
            c_upper[j,i]=min(surplus,max((E_MAX-low)/ETA_C,0.))
            r_upper[j,i]=min(deficit,max(ETA_D*(high-E_MIN),0.))
            # 这些界由旧 fast LP 已有的 c<=surplus、r<=deficit、SOC 方程直接蕴含。
            # 因而它们包含旧 formulation 的全部 LP/MIP 可行点，不依赖某个 incumbent。
            low=max(E_MIN,low-deficit/ETA_D)
            high=min(E_MAX,high+ETA_C*surplus)
            e_lower[j,i]=max(E_MIN,np.nextafter(low,-np.inf))
            e_upper[j,i]=min(E_MAX,np.nextafter(high,np.inf))
            c_upper[j,i]=min(CAP,np.nextafter(c_upper[j,i],np.inf))
            r_upper[j,i]=min(CAP,np.nextafter(r_upper[j,i],np.inf))
    return e_lower,e_upper,c_upper,r_upper

def build_base(net, prices, weights, initial_soc, *, grid_upper, fixed_policy=None):
    net, prices, weights = [np.asarray(v, dtype=float) for v in (net, prices, weights)]
    if net.ndim != 2 or prices.shape != (net.shape[1],) or weights.shape != (net.shape[0],):
        raise ValueError("场景/电价/概率维度不符")
    if not all(np.isfinite(v).all() for v in (net, prices, weights)) or (prices <= 0).any() or (weights <= 0).any():
        raise ValueError("输入必须有限且电价/概率为正")
    if not np.isclose(weights.sum(), 1, atol=1e-12) or not E_MIN <= initial_soc <= E_MAX:
        raise ValueError("概率或初态不符")
    s, t = net.shape
    g, cp, rp = [np.arange(k*t, (k+1)*t) for k in range(3)]
    blocks = [np.arange(3*t+k*s*t, 3*t+(k+1)*s*t).reshape(s, t) for k in range(12)]
    c, r, q, w, e, z, *selectors = blocks
    lr, lc = selectors[:3], selectors[3:]
    size = 3*t+12*s*t
    objective, lo, hi, integer = np.zeros(size), np.zeros(size), np.full(size, np.inf), np.zeros(size)
    grid_upper = np.asarray(grid_upper, dtype=float)
    objective[g] = prices; objective[q] = 5*weights[:, None]*prices
    hi[g], hi[cp], hi[rp] = grid_upper, CAP, CAP
    hi[c], hi[r], hi[q], hi[w] = CAP, CAP, np.maximum(net, 0), np.maximum(grid_upper-net, 0)
    lo[e], hi[e] = E_MIN, E_MAX
    for block in (z, *lr, *lc):
        hi[block] = 1; integer[block] = 1
    hi[z[net < 0]] = 0
    free_charge = fixed_policy is None
    if free_charge:
        # z=sum(lr)，且lr为二元变量、z在[0,1]；z的整数性已由等式隐含。
        integer[z] = 0
        for block in lc:
            hi[block] = 0; integer[block] = 0
    if fixed_policy is None:
        # 单段反馈下提高充电上限使逐步SOC不减、紧急购电不增；见等价性文档的支配性证明。
        # 仅优化时消去被支配的选择；固定策略回放必须保留调用者指定的上限。
        lo[cp] = CAP
    else:
        if fixed_policy.charge_cap.shape != (t,) or fixed_policy.grid.shape != (t,):
            raise ValueError("线性编码只支持单段策略")
        for indices, values in ((g, fixed_policy.grid), (cp, fixed_policy.charge_cap), (rp, fixed_policy.discharge_cap)):
            if (values < lo[indices]-1e-8).any() or (values > hi[indices]+1e-8).any():
                raise ValueError("固定策略超出线性编码的物理上界")
            values = np.clip(values, lo[indices], hi[indices])
            lo[indices] = values; hi[indices] = values
    rows, cols, coefficients, lower, upper = [], [], [], [], []
    def add(terms, rhs, equal=False):
        index = len(upper)
        for column, value in terms:
            rows.append(index); cols.append(int(column)); coefficients.append(value)
        lower.append(rhs if equal else -np.inf); upper.append(rhs)
    for j in range(s):
        for i in range(t):
            n = float(net[j, i]); ci, ri, qi, wi, ei, zi = [int(v[j, i]) for v in (c, r, q, w, e, z)]
            previous = int(e[j, i-1]) if i else None
            add([(g[i], 1), (ri, 1), (qi, 1), (ci, -1), (wi, -1)], n, True)
            add([(ei, 1), (ci, -ETA_C), (ri, 1/ETA_D)]+([(previous, -1)] if i else []), 0 if i else initial_soc, True)
            add([(ci, 1), (cp[i], -1)], 0); add([(ri, 1), (rp[i], -1)], 0)
            room_max = (E_MAX-E_MIN)/ETA_C if i else (E_MAX-initial_soc)/ETA_C
            available_max = ETA_D*(E_MAX-E_MIN) if i else ETA_D*(initial_soc-E_MIN)
            add([(ci, 1)]+([(previous, 1/ETA_C)] if i else []), E_MAX/ETA_C if i else room_max)
            add([(ri, 1)]+([(previous, -ETA_D)] if i else []), -ETA_D*E_MIN if i else available_max)
            add([(ci, 1), (zi, CAP)], CAP); add([(ri, 1), (zi, -CAP)], 0)
            add([(qi, 1), (zi, -max(n, 0))], 0)
            surplus_max = max(float(grid_upper[i])-n, 0)
            add([(wi, 1), (zi, surplus_max)], surplus_max)
            add([(int(v[j, i]), 1) for v in lr]+[(zi, -1)], 0, True)
            if not free_charge:
                add([(int(v[j, i]), 1) for v in lc]+[(zi, 1)], 1, True)
            # 分支激活常数分别为：CAP、max(n,0)、可用电量上界，以及CAP、Gmax-n、容量空间上界。
            add([(rp[i], 1), (ri, -1), (lr[0][j, i], CAP)], CAP)
            deficit_max = max(n, 0)
            add([(g[i], -1), (ri, -1), (lr[1][j, i], deficit_max)], deficit_max-n)
            add([(ri, -1), (lr[2][j, i], available_max)]+([(previous, ETA_D)] if i else []),
                available_max+ETA_D*E_MIN if i else 0)
            if not free_charge:
                add([(cp[i], 1), (ci, -1), (lc[0][j, i], CAP)], CAP)
                add([(g[i], 1), (ci, -1), (lc[1][j, i], surplus_max)], surplus_max+n)
                add([(ci, -1), (lc[2][j, i], room_max)]+([(previous, -1/ETA_C)] if i else []),
                    room_max-E_MAX/ETA_C if i else 0)
            # 原整数反馈分支隐含的有效约束；仅加强松弛，不删除任何可行反馈策略。
            add([(qi, 1), (lr[0][j, i], -deficit_max), (lr[2][j, i], -deficit_max)], 0)
            if not free_charge:
                add([(wi, 1), (lc[0][j, i], -surplus_max), (lc[2][j, i], -surplus_max)], 0)
            add([(ei, 1), (lr[2][j, i], E_MAX-E_MIN)], E_MAX)
            if not free_charge:
                add([(ei, -1), (lc[2][j, i], E_MAX-E_MIN)], -E_MIN)
            # 同一方向的响应总量受净缺口/剩余上界约束，不能将分量上界重复相加。
            add([(ri, 1), (qi, 1), (zi, -deficit_max)], 0)
            add([(ci, 1), (wi, 1), (zi, surplus_max)], surplus_max)
            if i:
                # 当储能边界项为最小项，上一SOC必须在一时段功率可达的边界邻域。
                add([(previous, 1), (lr[2][j, i], E_MAX-E_MIN-CAP/ETA_D)], E_MAX)
                if not free_charge:
                    add([(previous, -1), (lc[2][j, i], E_MAX-E_MIN-ETA_C*CAP)], -E_MIN)
    matrix = coo_matrix((coefficients, (rows, cols)), shape=(len(upper), size)).tocsc()
    return objective, Bounds(lo, hi), integer, LinearConstraint(matrix, lower, upper), {"g": g, "cp": cp, "rp": rp,
                                                                                   "responses": (c, r, q, w, e), "z": z, "lr": lr, "lc": lc, "free_charge": free_charge}


def build_base_v2_free(net, prices, weights, initial_soc, *, grid_upper):
    """free aggregate 专用精确消元：不创建固定 cp/lc，并以 sum(lr) 代换 z。"""
    net,prices,weights=[np.asarray(v,dtype=float) for v in (net,prices,weights)]
    if net.ndim!=2 or prices.shape!=(net.shape[1],) or weights.shape!=(net.shape[0],):
        raise ValueError('场景/电价/概率维度不符')
    if not all(np.isfinite(v).all() for v in (net,prices,weights)) or (prices<=0).any() or (weights<=0).any():
        raise ValueError('输入必须有限且电价/概率为正')
    if not np.isclose(weights.sum(),1,atol=1e-12) or not E_MIN<=initial_soc<=E_MAX:
        raise ValueError('概率或初态不符')
    s,t=net.shape;grid_upper=np.asarray(grid_upper,dtype=float)
    g=np.arange(t);rp=np.arange(t,2*t)
    blocks=[np.arange(2*t+k*s*t,2*t+(k+1)*s*t).reshape(s,t) for k in range(8)]
    c,r,q,w,e,*lr=blocks;size=2*t+8*s*t
    objective=np.zeros(size);lo=np.zeros(size);hi=np.full(size,np.inf);integer=np.zeros(size)
    objective[g]=prices;objective[q]=5*weights[:,None]*prices
    hi[g],hi[rp]=grid_upper,CAP
    e_lo,e_hi,c_hi,r_hi=reachable_bounds(net,grid_upper,initial_soc)
    hi[c],hi[r]=c_hi,r_hi;hi[q]=np.maximum(net,0);hi[w]=np.maximum(grid_upper-net,0)
    lo[e],hi[e]=e_lo,e_hi
    for selector in lr:
        hi[selector]=1;integer[selector]=1;hi[selector][net<0]=0
    rows=[];cols=[];coefficients=[];lower=[];upper=[]
    def add(terms,rhs,equal=False):
        row=len(upper)
        for column,value in terms:
            rows.append(row);cols.append(int(column));coefficients.append(float(value))
        lower.append(rhs if equal else -np.inf);upper.append(rhs)
    for j in range(s):
        for i in range(t):
            n=float(net[j,i]);ci,ri,qi,wi,ei=[int(v[j,i]) for v in (c,r,q,w,e)]
            previous=int(e[j,i-1]) if i else None
            selectors=[int(v[j,i]) for v in lr];z=[(v,1.) for v in selectors]
            add([(g[i],1),(ri,1),(qi,1),(ci,-1),(wi,-1)],n,True)
            add([(ei,1),(ci,-ETA_C),(ri,1/ETA_D)]+([(previous,-1)] if i else []),0 if i else initial_soc,True)
            add([(ri,1),(rp[i],-1)],0)
            room_max=(E_MAX-E_MIN)/ETA_C if i else (E_MAX-initial_soc)/ETA_C
            available_max=ETA_D*(E_MAX-E_MIN) if i else ETA_D*(initial_soc-E_MIN)
            add([(ci,1)]+([(previous,1/ETA_C)] if i else []),E_MAX/ETA_C if i else room_max)
            add([(ri,1)]+([(previous,-ETA_D)] if i else []),-ETA_D*E_MIN if i else available_max)
            add([(ci,1)]+[(v,CAP) for v in selectors],CAP)
            add([(ri,1)]+[(v,-CAP) for v in selectors],0)
            deficit_max=max(n,0.);surplus_max=max(float(grid_upper[i])-n,0.)
            add([(qi,1)]+[(v,-deficit_max) for v in selectors],0)
            add([(wi,1)]+[(v,surplus_max) for v in selectors],surplus_max)
            # z∈[0,1] 与 z=sum(lr) 机械代换；n<0 时 selector 列界已固定为0。
            add(z,1.)
            add([(rp[i],1),(ri,-1),(selectors[0],CAP)],CAP)
            add([(g[i],-1),(ri,-1),(selectors[1],deficit_max)],deficit_max-n)
            add([(ri,-1),(selectors[2],available_max)]+([(previous,ETA_D)] if i else []),
                available_max+ETA_D*E_MIN if i else 0)
            add([(qi,1),(selectors[0],-deficit_max),(selectors[2],-deficit_max)],0)
            add([(ei,1),(selectors[2],E_MAX-E_MIN)],E_MAX)
            add([(ri,1),(qi,1)]+[(v,-deficit_max) for v in selectors],0)
            add([(ci,1),(wi,1)]+[(v,surplus_max) for v in selectors],surplus_max)
            if i:
                add([(previous,1),(selectors[2],E_MAX-E_MIN-CAP/ETA_D)],E_MAX)
    matrix=coo_matrix((coefficients,(rows,cols)),shape=(len(upper),size)).tocsc()
    indices={'g':g,'cp':np.array([],dtype=int),'rp':rp,'responses':(c,r,q,w,e),
             'z':np.array([],dtype=int),'lr':lr,'lc':(),'free_charge':True,'formulation':'v2_free'}
    return objective,Bounds(lo,hi),integer,LinearConstraint(matrix,lower,upper),indices


def build_base_v2_2bit(net, prices, weights, initial_soc, *, grid_upper):
    """四种物理模式的 2-bit 精确编码；仅作通过 LB 基准后才可生产的候选。"""
    net,prices,weights=[np.asarray(v,dtype=float) for v in (net,prices,weights)]
    if net.ndim!=2 or prices.shape!=(net.shape[1],) or weights.shape!=(net.shape[0],):
        raise ValueError('场景/电价/概率维度不符')
    if not all(np.isfinite(v).all() for v in (net,prices,weights)) or (prices<=0).any() or (weights<=0).any():
        raise ValueError('输入必须有限且电价/概率为正')
    if not np.isclose(weights.sum(),1,atol=1e-12) or not E_MIN<=initial_soc<=E_MAX:
        raise ValueError('概率或初态不符')
    s,t=net.shape;grid_upper=np.asarray(grid_upper,dtype=float)
    g=np.arange(t);rp=np.arange(t,2*t)
    blocks=[np.arange(2*t+k*s*t,2*t+(k+1)*s*t).reshape(s,t) for k in range(7)]
    c,r,q,w,e,b0,b1=blocks;size=2*t+7*s*t
    objective=np.zeros(size);lo=np.zeros(size);hi=np.full(size,np.inf);integer=np.zeros(size)
    objective[g]=prices;objective[q]=5*weights[:,None]*prices;hi[g],hi[rp]=grid_upper,CAP
    e_lo,e_hi,c_hi,r_hi=reachable_bounds(net,grid_upper,initial_soc)
    hi[c],hi[r]=c_hi,r_hi;hi[q]=np.maximum(net,0);hi[w]=np.maximum(grid_upper-net,0)
    lo[e],hi[e]=e_lo,e_hi
    for bit in (b0,b1):
        hi[bit]=1;integer[bit]=1;hi[bit][net<0]=0
    rows=[];cols=[];coefficients=[];lower=[];upper=[]
    def add(terms,rhs,equal=False):
        row=len(upper)
        for column,value in terms:
            rows.append(row);cols.append(int(column));coefficients.append(float(value))
        lower.append(rhs if equal else -np.inf);upper.append(rhs)
    for j in range(s):
        for i in range(t):
            n=float(net[j,i]);ci,ri,qi,wi,ei,first,second=[int(v[j,i]) for v in (c,r,q,w,e,b0,b1)]
            previous=int(e[j,i-1]) if i else None
            deficit=max(n,0.);surplus=max(float(grid_upper[i])-n,0.)
            previous_high=initial_soc if i==0 else e_hi[j,i-1]
            available=max(0.,ETA_D*(previous_high-E_MIN))
            add([(g[i],1),(ri,1),(qi,1),(ci,-1),(wi,-1)],n,True)
            add([(ei,1),(ci,-ETA_C),(ri,1/ETA_D)]+([(previous,-1)] if i else []),0 if i else initial_soc,True)
            add([(ri,1),(rp[i],-1)],0)
            room=(E_MAX-E_MIN)/ETA_C if i else (E_MAX-initial_soc)/ETA_C
            add([(ci,1)]+([(previous,1/ETA_C)] if i else []),E_MAX/ETA_C if i else room)
            add([(ri,1)]+([(previous,-ETA_D)] if i else []),-ETA_D*E_MIN if i else available)
            # 00=充电，01=rp最小，10=deficit最小，11=available最小。
            add([(ci,1),(first,CAP)],CAP);add([(ci,1),(second,CAP)],CAP)
            add([(ri,1),(first,-CAP),(second,-CAP)],0)
            add([(qi,1),(first,-deficit),(second,-deficit)],0)
            add([(wi,1),(first,surplus)],surplus);add([(wi,1),(second,surplus)],surplus)
            # 被编码模式的候选值必须等于 r；上界 r<=三个候选由共享约束/平衡给出。
            add([(rp[i],1),(ri,-1),(first,-CAP),(second,CAP)],CAP)
            add([(g[i],-1),(ri,-1),(first,deficit),(second,-deficit)],deficit-n)
            add([(ri,-1),(first,available),(second,available)]+([(previous,ETA_D)] if i else []),
                2*available+ETA_D*E_MIN if i else 2*available-ETA_D*(initial_soc-E_MIN))
            # q只可能在rp或available为最小的编码（第二位=1）中为正。
            add([(qi,1),(second,-deficit)],0)
            span=E_MAX-E_MIN
            add([(ei,1),(first,span),(second,span)],E_MIN+2*span)
            add([(ri,1),(qi,1)],deficit);add([(ci,1),(wi,1)],surplus)
            if i:
                threshold=E_MIN+CAP/ETA_D;big=max(0.,E_MAX-threshold)
                add([(previous,1),(first,big),(second,big)],threshold+2*big)
    matrix=coo_matrix((coefficients,(rows,cols)),shape=(len(upper),size)).tocsc()
    indices={'g':g,'cp':np.array([],dtype=int),'rp':rp,'responses':(c,r,q,w,e),
             'z':np.array([],dtype=int),'lr':(),'lc':(),'bits':(b0,b1),'free_charge':True,
             'formulation':'v2_2bit'}
    return objective,Bounds(lo,hi),integer,LinearConstraint(matrix,lower,upper),indices


def _finish_matrix(objective,bounds,integer,constraints,indices,scenes,prices,*,reference,today,terminal):
    """旧版与 v2 共用终端项、有效前缀序和非对称调整成本。"""
    objective[indices['responses'][4][:,-1]]=-terminal*scenes.weights
    rows=[];cols=[];vals=[];rhs=[]
    e=indices['responses'][4];q=indices['responses'][2];w=indices['responses'][3];net=scenes.net
    for a in range(len(net)):
        for b in range(len(net)):
            if a==b:continue
            ordered=np.flatnonzero(np.maximum.accumulate(net[a]-net[b])<=0.)
            for t in ordered:
                for block,sign in ((e,-1.),(q,1.),(w,-1.)):
                    row=len(rhs);rows.extend([row,row]);cols.extend([block[a,t],block[b,t]])
                    vals.extend([sign,-sign]);rhs.append(0.)
    if rhs:
        addition=coo_matrix((vals,(rows,cols)),shape=(len(rhs),len(objective))).tocsc()
        constraints=LinearConstraint(vstack([constraints.A,addition]).tocsc(),
            np.r_[constraints.lb,np.full(len(rhs),-np.inf)],np.r_[constraints.ub,rhs])
    today=min(today,len(prices));indices['adjustment']=np.array([],dtype=int)
    if reference is not None:
        count=len(objective);extra=np.arange(count,count+today);indices['adjustment']=extra
        objective[indices['g'][:today]]=0.;objective=np.r_[objective,np.ones(today)]
        upper=np.maximum(scenes.net.max(0),0)+CAP
        lo=-.5*prices[:today]*reference[:today];delta=upper[:today]-reference[:today]
        hi=prices[:today]*np.maximum(.5*delta,1.5*delta)
        bounds=Bounds(np.r_[bounds.lb,lo],np.r_[bounds.ub,hi]);integer=np.r_[integer,np.zeros(today)]
        rows=[];cols=[];vals=[];rhs=[]
        for t in range(today):
            for slope in (.5,1.5):
                row=len(rhs);rows.extend([row,row]);cols.extend([indices['g'][t],extra[t]])
                vals.extend([slope*prices[t],-1.]);rhs.append(slope*prices[t]*reference[t])
        additional=coo_matrix((vals,(rows,cols)),shape=(len(rhs),len(objective))).tocsc()
        matrix=vstack([hstack([constraints.A,coo_matrix((constraints.A.shape[0],today))]),additional]).tocsc()
        constraints=LinearConstraint(matrix,np.r_[constraints.lb,np.full(len(rhs),-np.inf)],np.r_[constraints.ub,rhs])
    return objective,bounds,integer,constraints,indices


def linear_seed(policy, net, initial_soc, indices, size):
    vector = np.zeros(size)
    for key, values in (("g", policy.grid), ("cp", policy.charge_cap), ("rp", policy.discharge_cap)):
        vector[indices[key]] = values
    for j, path in enumerate(net):
        response = replay(policy, path, initial_soc)
        for columns, key in zip(indices["responses"], ("charge", "discharge", "emergency", "spill", "soc")):
            vector[columns[j]] = response[key]
        previous = initial_soc
        for i, n in enumerate(path):
            x = n-policy.grid[i]; deficit = x >= 0
            vector[indices["z"][j, i]] = int(deficit)
            rmin = np.argmin([policy.discharge_cap[i], max(x, 0), ETA_D*(previous-E_MIN)])
            cmin = np.argmin([policy.charge_cap[i], max(-x, 0), (E_MAX-previous)/ETA_C])
            if deficit:
                vector[indices["lr"][rmin][j, i]] = 1
            elif not indices["free_charge"]:
                vector[indices["lc"][cmin][j, i]] = 1
            previous = response["soc"][i]
    return vector



def build_matrix(scenes: Scenarios, prices: np.ndarray, initial: float, *, reference=None,
                 today: int=144, terminal: float=0., fixed_policy: Policy | None=None) -> tuple:
    if terminal < 0:
        raise ValueError('单调充电证明仅适用于非负终端残值')
    # 自由优化时削去必定成为spill的购电：超过max(n,0)+CAP不改变任何场景的储能动作。
    upper = scenes.load.max(0)/6+CAP if fixed_policy is not None else np.maximum(scenes.net.max(0),0)+CAP
    objective, bounds, integer, constraints, indices = build_base(scenes.net, prices, scenes.weights, initial,
        grid_upper=upper, fixed_policy=fixed_policy)
    objective[indices['responses'][4][:,-1]] = -terminal*scenes.weights
    if fixed_policy is None:
        # 已知净负荷前缀逐点支配蕴含原反馈SOC/q/spill次序；只加入原模型必然满足的有效约束。
        rows=[];cols=[];vals=[];rhs=[]
        e=indices['responses'][4];q=indices['responses'][2];w=indices['responses'][3]
        net=scenes.net
        for a in range(len(net)):
            for b in range(len(net)):
                if a==b:continue
                ordered=np.flatnonzero(np.maximum.accumulate(net[a]-net[b])<=0.)
                for t in ordered:
                    for block,sign in ((e,-1.),(q,1.),(w,-1.)):
                        row=len(rhs);rows.extend([row,row]);cols.extend([block[a,t],block[b,t]])
                        vals.extend([sign,-sign]);rhs.append(0.)
        if rhs:
            addition=coo_matrix((vals,(rows,cols)),shape=(len(rhs),len(objective))).tocsc()
            constraints=LinearConstraint(vstack([constraints.A,addition]).tocsc(),
                np.r_[constraints.lb,np.full(len(rhs),-np.inf)],np.r_[constraints.ub,rhs])
    today = min(today, len(prices))
    indices['adjustment'] = np.array([],dtype=int)
    if reference is not None:
        count=len(objective);extra=np.arange(count,count+today);indices['adjustment']=extra
        objective[indices['g'][:today]]=0.
        objective=np.r_[objective,np.ones(today)]
        lo=-.5*prices[:today]*reference[:today]
        delta=upper[:today]-reference[:today]
        hi=prices[:today]*np.maximum(.5*delta,1.5*delta)
        bounds=Bounds(np.r_[bounds.lb,lo],np.r_[bounds.ub,hi])
        integer=np.r_[integer,np.zeros(today)]
        rows=[];cols=[];vals=[];rhs=[]
        for t in range(today):
            for slope in (.5,1.5):
                row=len(rhs);rows.extend([row,row]);cols.extend([indices['g'][t],extra[t]])
                vals.extend([slope*prices[t],-1.]);rhs.append(slope*prices[t]*reference[t])
        additional=coo_matrix((vals,(rows,cols)),shape=(len(rhs),len(objective))).tocsc()
        matrix=vstack([hstack([constraints.A,coo_matrix((constraints.A.shape[0],today))]),additional]).tocsc()
        constraints=LinearConstraint(matrix,np.r_[constraints.lb,np.full(len(rhs),-np.inf)],np.r_[constraints.ub,rhs])
    return objective,bounds,integer,constraints,indices


def build_matrix_v2_free(scenes: Scenarios, prices: np.ndarray, initial: float, *, reference=None,
                         today: int=144, terminal: float=0.) -> tuple:
    """仅用于自由 aggregate 策略；旧 build_matrix 保留作固定策略与回归基准。"""
    if terminal<0:raise ValueError('单调充电证明仅适用于非负终端残值')
    upper=np.maximum(scenes.net.max(0),0)+CAP
    result=build_base_v2_free(scenes.net,prices,scenes.weights,initial,grid_upper=upper)
    return _finish_matrix(*result,scenes,prices,reference=reference,today=today,terminal=terminal)


def build_matrix_v2_2bit(scenes: Scenarios, prices: np.ndarray, initial: float, *, reference=None,
                         today: int=144, terminal: float=0.) -> tuple:
    if terminal<0:raise ValueError('单调充电证明仅适用于非负终端残值')
    upper=np.maximum(scenes.net.max(0),0)+CAP
    result=build_base_v2_2bit(scenes.net,prices,scenes.weights,initial,grid_upper=upper)
    return _finish_matrix(*result,scenes,prices,reference=reference,today=today,terminal=terminal)


def linear_seed_v2_free(policy: Policy, net: np.ndarray, initial: float, indices: dict, size: int) -> np.ndarray:
    vector=np.zeros(size);vector[indices['g']]=policy.grid;vector[indices['rp']]=policy.discharge_cap
    for j,path in enumerate(net):
        response=replay(policy,path,initial)
        for columns,key in zip(indices['responses'],('charge','discharge','emergency','spill','soc')):
            vector[columns[j]]=response[key]
        previous=initial
        for i,n in enumerate(path):
            x=n-policy.grid[i]
            if x>=0:
                branch=int(np.argmin([policy.discharge_cap[i],max(x,0),ETA_D*(previous-E_MIN)]))
                vector[indices['lr'][branch][j,i]]=1
            previous=response['soc'][i]
    return vector


def linear_seed_v2_2bit(policy: Policy, net: np.ndarray, initial: float, indices: dict, size: int) -> np.ndarray:
    vector=np.zeros(size);vector[indices['g']]=policy.grid;vector[indices['rp']]=policy.discharge_cap
    b0,b1=indices['bits']
    for j,path in enumerate(net):
        response=replay(policy,path,initial)
        for columns,key in zip(indices['responses'],('charge','discharge','emergency','spill','soc')):
            vector[columns[j]]=response[key]
        previous=initial
        for i,n in enumerate(path):
            x=n-policy.grid[i]
            if x>=0:
                branch=int(np.argmin([policy.discharge_cap[i],max(x,0),ETA_D*(previous-E_MIN)]))
                vector[b0[j,i]]=float(branch in (1,2));vector[b1[j,i]]=float(branch in (0,2))
            previous=response['soc'][i]
    return vector


def seed_vector(policy: Policy, scenes: Scenarios, prices: np.ndarray, initial: float,
                indices: dict, size: int, reference: np.ndarray | None) -> np.ndarray:
    formulation=indices.get('formulation')
    vector=(linear_seed_v2_free(policy,scenes.net,initial,indices,size) if formulation=='v2_free'
            else linear_seed_v2_2bit(policy,scenes.net,initial,indices,size) if formulation=='v2_2bit'
            else linear_seed(policy,scenes.net,initial,indices,size))
    if len(indices['adjustment']):
        n=len(indices['adjustment']);vector[indices['adjustment']]=adjustment(policy.grid[:n],reference[:n],prices[:n])
    return vector


def matrix_error(vector, bounds, integer, constraints) -> tuple[float,float]:
    if not np.isfinite(vector).all():return float('inf'),float('inf')
    bound_error=max(0.,float(np.max(bounds.lb-vector)),float(np.max(vector-bounds.ub)))
    if bound_error>TOL:return bound_error,float('inf')
    activity=constraints.A@vector
    if not np.isfinite(activity).all():return float('inf'),float('inf')
    feasibility=max(0.,float(np.max(bounds.lb-vector)),float(np.max(vector-bounds.ub)),
                    float(np.max(constraints.lb-activity)),float(np.max(activity-constraints.ub)))
    integrality=float(np.max(abs(vector[integer==1]-np.rint(vector[integer==1]))))
    return feasibility,integrality


def solve_fast(scenes: Scenarios, prices: np.ndarray, initial: float, config: Config, *, reference=None,
               today: int=144, terminal: float=0., seed: Policy | None=None, known_lower: float | None=None,
               fixed_policy: Policy | None=None, seconds: float | None=None, progress=None,
               formulation: str | None=None, known_lower_provenance: dict | None=None,
               deadline: float | None=None) -> tuple:
    from .optimization import objective as policy_objective
    if config.feedback!='aggregate':
        raise ValueError('lag反馈不能使用单调充电简化')
    started=time.perf_counter()
    formulation=config.formulation if formulation is None else formulation
    if config.solver_backend not in ('auto','highs'):
        from .gurobi_backend import GurobiUnavailable
        raise GurobiUnavailable('正式Gurobi后端未启用：当前许可证不能承载Q3完整矩阵')
    if formulation not in ('legacy','v2_free','v2_2bit'):raise ValueError('未知 fast formulation')
    if fixed_policy is not None:formulation='legacy'
    builder=build_matrix_v2_free if formulation=='v2_free' else build_matrix_v2_2bit if formulation=='v2_2bit' else build_matrix
    objective,bounds,integer,constraints,indices=builder(scenes,prices,initial,reference=reference,
        today=today,terminal=terminal,**({'fixed_policy':fixed_policy} if formulation=='legacy' else {}))
    if fixed_policy is not None:seed=fixed_policy
    elif seed is not None:seed=Policy(np.minimum(seed.grid,np.maximum(scenes.net.max(0),0)+CAP),np.full(len(prices),CAP),seed.discharge_cap.copy())
    vector=seed_vector(seed,scenes,prices,initial,indices,len(objective),reference) if seed else None
    if vector is not None:
        feasibility,integrality=matrix_error(vector,bounds,integer,constraints)
        if feasibility>TOL or integrality>1e-8:raise ValueError(f'热启动向量不可行: {feasibility}/{integrality}')
    highs_core._Highs.resetGlobalScheduler(True);solver=HighsAPI()
    requested_solver_seconds=seconds or config.seconds
    options={'threads':config.solver_threads,'parallel':'on' if config.solver_threads>1 else 'off',
        # 原 replay 目标可能小于内部松弛目标，停止条件只能由下方 assess 回调判定。
        # MIP logging callback is the periodic durability clock; suppress console/file text separately.
        'output_flag':True,'log_to_console':False,'mip_rel_gap':0.,
        'mip_min_logging_interval':1.,
        'mip_feasibility_tolerance':1e-8,'primal_feasibility_tolerance':1e-8}
    if config.solver_focus=='bound':
        options.update(mip_heuristic_effort=0.,mip_heuristic_run_feasibility_jump=False,
            mip_heuristic_run_rens=False,mip_heuristic_run_rins=False,
            mip_heuristic_run_root_reduced_cost=False,mip_heuristic_run_shifting=False,
            mip_heuristic_run_zi_round=False)
    for key,value in options.items():
        if solver.setOptionValue(key,value)==highs_core.HighsStatus.kError:raise ValueError(f'HiGHS不接受参数{key}')
    lp=highs_core.HighsLp();matrix=constraints.A
    lp.num_col_,lp.num_row_=len(objective),matrix.shape[0]
    lp.col_cost_,lp.col_lower_,lp.col_upper_=objective,bounds.lb,bounds.ub
    lp.row_lower_,lp.row_upper_=constraints.lb,constraints.ub
    lp.a_matrix_.num_col_,lp.a_matrix_.num_row_=lp.num_col_,lp.num_row_
    lp.a_matrix_.format_=highs_core.MatrixFormat.kColwise
    lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=matrix.indptr,matrix.indices,matrix.data
    lp.integrality_=[highs_core.HighsVarType(int(v)) for v in integer]
    if solver.passModel(lp)==highs_core.HighsStatus.kError:raise ValueError('HiGHS模型加载失败')
    solver_seconds=requested_solver_seconds
    if deadline is not None:solver_seconds=max(.01,min(solver_seconds,deadline-time.perf_counter()))
    if solver.setOptionValue('time_limit',solver_seconds)==highs_core.HighsStatus.kError:
        raise ValueError('HiGHS不接受剩余hard wall')
    if vector is not None:
        hs=highs_core.HighsSolution();hs.col_value=vector;hs.value_valid=True
        if solver.setSolution(hs)==highs_core.HighsStatus.kError:raise ValueError('HiGHS拒绝已验收的初值')
    digest=matrix_digest(objective,bounds,integer,constraints)
    if (known_lower is not None and known_lower_provenance and known_lower_provenance.get('kind')=='checkpoint'
            and known_lower_provenance.get('matrix_digest')!=digest):
        raise ValueError('不同 formulation/matrix 的检查点下界禁止复用')
    bound_sources=[{'kind':'solver_global_bound','matrix_digest':digest}]
    if known_lower is not None:
        bound_sources.append(known_lower_provenance or {'kind':'unspecified_valid_bound'})
    callback_counts={}
    base_audit={'status':'searching','solver':'HiGHS_Q3_monotone_equivalent_MILP',
        'solver_version':solver.version(),'binaries':int(integer.sum()),'variables':len(objective),
        'constraints':matrix.shape[0],'scenario_count':len(scenes.weights),'requested_gap':config.gap,
        'terminal':terminal,'solver_threads':config.solver_threads,'formulation_version':formulation,
        'matrix_digest':digest,'objective_offset':0.,'bound_sources':bound_sources,
        'solver_backend_requested':config.solver_backend,'solver_focus':config.solver_focus,
        'solver_time_limit':solver_seconds,
        'callback_counts':callback_counts,'reliable':False}
    def assess(vector: np.ndarray, lower: float) -> tuple:
        policy=Policy(np.maximum(vector[indices['g']],0),
            np.full(len(prices),CAP) if formulation!='legacy' else np.maximum(vector[indices['cp']],0),
            np.maximum(vector[indices['rp']],0))
        responses=[replay(policy,path,initial) for path in scenes.net]
        raw=np.stack([vector[v] for v in indices['responses']],axis=-1)
        exact=np.array([np.array([row[k] for k in ('charge','discharge','emergency','spill','soc')]).T for row in responses])
        feasibility,integrality=matrix_error(vector,bounds,integer,constraints)
        projection=max(0.,float(np.max(raw[...,4]-exact[...,4])),float(np.max(exact[...,2]-raw[...,2])))
        difference=float(np.max(abs(raw-exact)))
        value=policy_objective(policy,responses,scenes.weights,prices,reference,min(today,len(prices)),terminal)
        raw_value=float(objective@vector)
        gap=max(0.,value-lower)/max(abs(value),1e-10)
        valid=(feasibility<=TOL and integrality<=1e-8 and value<=raw_value+TOL and lower<=value+TOL
               and (difference if fixed_policy is not None else projection)<=TOL)
        audit={**base_audit}
        audit.update(objective=value,upper_bound=value,optimizer_objective=raw_value,gap=gap,linear_feasibility_error=feasibility,
            integrality_error=integrality,monotone_projection_error=projection,raw_response_difference=difference,
            mapping_error=difference if fixed_policy is not None else None,
            mapped_cost_not_above_optimizer=bool(value<=raw_value+TOL),
            reliable=bool(valid and value-lower<=max(TOL,config.gap*abs(value))))
        if not valid:raise ValueError(f'单调等价模型证书不符: {audit}')
        return policy,responses,audit
    cached_vector=vector.copy() if vector is not None else None
    current_lower=known_lower if known_lower is not None else -float('inf')
    last_save=0.;last_archive=0;cached_assessed_value=None;callback_error=[]
    if cached_vector is not None and np.isfinite(current_lower):
        _,_,initial_audit=assess(cached_vector,current_lower);cached_assessed_value=initial_audit['objective']
    def callback(event):
        nonlocal cached_vector,current_lower,last_save,last_archive,cached_assessed_value
        kind=int(event.callback_type);output=event.data_out;improved=False
        callback_counts[str(kind)]=callback_counts.get(str(kind),0)+1
        if np.isfinite(output.mip_dual_bound):current_lower=max(current_lower,float(output.mip_dual_bound))
        if kind in (int(highs_core.cb.kCallbackMipImprovingSolution),int(highs_core.cb.kCallbackMipSolution)):
            candidate=np.asarray(output.mip_solution).copy()
            if len(candidate)==len(objective) and np.isfinite(candidate).all():
                feasible,integral=matrix_error(candidate,bounds,integer,constraints)
                if feasible<=TOL and integral<=1e-8 and (cached_vector is None or objective@candidate<objective@cached_vector):
                    cached_vector=candidate.copy();cached_assessed_value=None;improved=True
        elapsed=time.perf_counter()-started;archive=int(elapsed//120)
        if improved and np.isfinite(current_lower):
            try:
                policy,responses,audit=assess(cached_vector,current_lower);cached_assessed_value=audit['objective']
                if audit['reliable']:
                    audit.update(seconds=elapsed,lower_bound=current_lower,solver_seconds=float(output.running_time),
                        node_count=int(output.mip_node_count),simplex_iterations=int(output.simplex_iteration_count),
                        barrier_iterations=int(output.ipm_iteration_count))
                    if progress is not None:progress(policy,responses,audit)
                    last_save=elapsed;last_archive=archive;event.interrupt();return
            except Exception as error:
                callback_error.append(error);event.interrupt();return
        certificate_due=(cached_assessed_value is not None and
            cached_assessed_value-current_lower<=max(TOL,config.gap*abs(cached_assessed_value)))
        durable_due=elapsed-last_save>=30 or archive>last_archive
        if progress is not None and cached_vector is not None and np.isfinite(current_lower) and (certificate_due or durable_due):
            try:
                policy,responses,audit=assess(cached_vector,current_lower)
                audit.update(seconds=elapsed,lower_bound=current_lower)
                audit.update(solver_seconds=float(output.running_time),node_count=int(output.mip_node_count),
                             simplex_iterations=int(output.simplex_iteration_count),
                             barrier_iterations=int(output.ipm_iteration_count))
                progress(policy,responses,audit)
                last_save=elapsed;last_archive=archive;cached_assessed_value=audit['objective']
                if audit['reliable']:event.interrupt()
            except Exception as error:
                callback_error.append(error);event.interrupt()
    if progress is not None:
        solver.cbMipImprovingSolution+=callback;solver.cbMipSolution+=callback
        solver.cbMipLogging+=callback;solver.cbMipInterrupt+=callback
    if solver.run()==highs_core.HighsStatus.kError:raise ValueError('HiGHS运行失败')
    if callback_error:raise callback_error[0]
    info=solver.getInfo();lower=float(info.mip_dual_bound)
    if known_lower is not None:lower=max(lower,known_lower)
    lower=max(lower,current_lower)
    base_audit.update(status=solver.modelStatusToString(solver.getModelStatus()),seconds=time.perf_counter()-started,
                      solver_seconds=float(solver.getRunTime()),lower_bound=lower if np.isfinite(lower) else None,
                      node_count=int(info.mip_node_count),simplex_iterations=int(info.simplex_iteration_count),
                      barrier_iterations=int(info.ipm_iteration_count))
    if info.primal_solution_status==highs_core.kSolutionStatusFeasible:
        final=np.asarray(solver.getSolution().col_value)
        if cached_vector is None or objective@final<objective@cached_vector:cached_vector=final
    if cached_vector is None:return None,[],base_audit
    policy,responses,audit=assess(cached_vector,lower)
    if progress is not None:progress(policy,responses,audit)
    return policy,responses,audit
