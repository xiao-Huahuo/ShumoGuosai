"""Restore the original computation files from the compact support-data cache."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import lzma

ROOT = Path(__file__).resolve().parents[1]


def restore(destination):
    destination = Path(destination).resolve()
    index = json.loads((ROOT / "缓存目录.json").read_text(encoding="utf-8"))
    cache = ROOT / "计算缓存.dat.xz"
    if hashlib.sha256(cache.read_bytes()).hexdigest() != index["compressed_sha256"]:
        raise ValueError("计算缓存校验失败，请重新解压完整ZIP")
    count = 0
    with lzma.open(cache, "rb") as stream:
        for record in index["records"]:
            data = stream.read(record["bytes"])
            if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("缓存内容校验失败")
            for name in record["paths"]:
                relative = PurePosixPath(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("缓存目录含非法路径")
                target = destination.joinpath(*relative.parts)
                if not target.resolve().is_relative_to(destination):
                    raise ValueError("目标路径超出材料目录")
                if target.exists():
                    if hashlib.sha256(target.read_bytes()).hexdigest() != record["sha256"]:
                        raise ValueError(f"已有文件不同，未覆盖：{name}")
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                count += 1
        if stream.read(1):
            raise ValueError("缓存包含目录外的额外内容")
    return count


if __name__ == "__main__":
    print(f"已恢复并校验 {restore(ROOT)} 份数据文件。")
    print("运行第二问敏感性实验前，请按运行说明重建四份可再生成的实验数组。")
