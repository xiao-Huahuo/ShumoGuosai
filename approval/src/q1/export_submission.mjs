// Run from the project root with the bundled @oai/artifact-tool dependency.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { FileBlob, SpreadsheetFile, Workbook } from '@oai/artifact-tool';

const root = process.cwd();
const qa = path.join(root, 'docs/final_submission');
const template = path.join(root, 'docs/CUMCM2026Problems/C题/附件/附件5/result1.xlsx');
const source = path.join(root, 'outputs/.q1-runs/run-ie6fkatf/processed');
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(template));
await fs.mkdir(qa, { recursive: true });

async function render(name, sheetName, range) {
  const blob = await workbook.render({ sheetName, range, scale: 2, format: 'png' });
  await fs.writeFile(path.join(qa, `${name}.png`), new Uint8Array(await blob.arrayBuffer()));
}

if (process.argv.includes('--preview-only')) {
  console.log((await workbook.inspect({ kind: 'sheet', include: 'id,name' })).ndjson);
  await render('template_plan', '计划购电量', 'A1:B14');
  await render('template_storage', '充放电量', 'A1:E7');
} else {
  const csv = await Workbook.fromCSV(await fs.readFile(path.join(source, 'result1.csv'), 'utf8'), { sheetName: 'Source' });
  const [headers, ...records] = csv.worksheets.getItem('Source').getUsedRange().values;
  const rows = records.filter(row => row[0] !== null && row[0] !== '');
  if (rows.length !== 144) throw new Error(`Expected 144 intervals, got ${rows.length}`);
  const index = name => {
    const i = headers.indexOf(name);
    if (i < 0) throw new Error(`Missing source field ${name}`);
    return i;
  };
  const num = (row, name) => {
    const value = Number(row[index(name)]);
    if (!Number.isFinite(value)) throw new Error(`Non-finite ${name}`);
    return value;
  };
  const stamp = minutes => `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
  const planValues = rows.map((row, i) => {
    const interval = `${stamp(i * 10)}-${stamp((i + 1) * 10)}`;
    if (row[index('interval')] !== interval || num(row, 't') !== i + 1) throw new Error(`Interval mismatch at ${i + 1}`);
    return [interval, num(row, 'G_kwh')];
  });
  const plan = workbook.worksheets.getItem('计划购电量');
  const originalIntervals = plan.getRange('A2:A145').values.flat();
  plan.getRange('A2:B145').values = planValues;
  plan.getRange('A1:A145').format.columnWidth = 20;
  plan.getRange('B1:B145').format.columnWidth = 18;
  plan.getRange('B2:B145').setNumberFormat('0.0000');

  const storage = workbook.worksheets.getItem('充放电量');
  const blocks = Array.from({ length: 6 }, (_, i) => rows.slice(i * 24, (i + 1) * 24));
  storage.getRange('B2:C7').values = blocks.map(block => ['C_kwh', 'D_kwh'].map(key => block.reduce((sum, row) => sum + num(row, key), 0)));
  storage.getRange('E2:E3').values = [[num(rows[0], 'E_start_kwh')], [num(rows[143], 'E_kwh')]];
  storage.getRange('A1:A7').format.columnWidth = 19;
  storage.getRange('B1:C7').format.columnWidth = 17;
  storage.getRange('E1:E7').format.columnWidth = 17;
  storage.getRange('B2:C7').setNumberFormat('0.0000');
  storage.getRange('E2:E3').setNumberFormat('0.0000');

  const inspection = await workbook.inspect({ kind: 'table', range: '充放电量!A1:E7', include: 'values,formulas', tableMaxRows: 7, tableMaxCols: 5 });
  const errors = await workbook.inspect({ kind: 'match', searchTerm: '#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!', options: { useRegex: true, maxResults: 20 } });
  await fs.writeFile(path.join(qa, 'artifact_inspection.ndjson'), `${inspection.ndjson}\n${errors.ndjson}\n`, 'utf8');
  await render('result1_plan_start', '计划购电量', 'A1:B15');
  await render('result1_plan_middle', '计划购电量', 'A57:B75');
  await render('result1_plan_end', '计划购电量', 'A132:B145');
  await render('result1_storage', '充放电量', 'A1:E7');
  const output = path.join(root, 'outputs/final/result1.xlsx');
  await fs.mkdir(path.dirname(output), { recursive: true });
  await (await SpreadsheetFile.exportXlsx(workbook)).save(output);
  const sidecar = `${output}.inspect.ndjson`;
  if (await fs.stat(sidecar).catch(() => null)) await fs.rename(sidecar, path.join(qa, 'result1.xlsx.inspect.ndjson'));
  const hashes = {};
  for (const file of [template, ...['result1.csv', 'table2_storage.csv', 'table1_purchase.csv', 'daily_summary.csv'].map(name => path.join(source, name))]) {
    hashes[path.relative(root, file)] = createHash('sha256').update(await fs.readFile(file)).digest('hex');
  }
  await fs.writeFile(path.join(qa, 'result1_export.json'), JSON.stringify({ template: path.relative(root, template), source: path.relative(root, source), output: path.relative(root, output), originalIntervals, correctedIntervals: planValues.map(row => row[0]), reason: 'Template labels are shifted by ten minutes; align with the verified 144 source intervals from 00:00 to 24:00, as in the other four official outputs.', source_sha256: hashes }, null, 2) + '\n', 'utf8');
  console.log(`Exported ${output}`);
  console.log(inspection.ndjson);
  console.log(errors.ndjson);
}
