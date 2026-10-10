# packing-3d-research

外贸装箱（Container Loading）3D 研究项目：自动排箱 API + React Three Fiber 预览。

引擎在柜内上限里做紧凑排箱，并带承重、重心带和 LIFO 装卸顺序。前端可改 SKU、导入表格、看 3D、在柜内拖箱子，并导出装箱单。

详细调研见根目录 [REPORT.md](./REPORT.md)，一页摘要见 [docs/SUMMARY.md](./docs/SUMMARY.md)。

## 目录

```
packing-3d-research/
  REPORT.md          # 技术调研（必读）
  docs/SUMMARY.md
  backend/           # FastAPI + Extreme-Point 紧凑排箱（承重 / 重心 / LIFO）
  frontend/          # Vite + React + R3F 可视化
```

## 环境

- Python 3.10+
- Node.js 18+

## 后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 健康检查：`GET http://127.0.0.1:8000/api/health`
- 示例请求：`GET http://127.0.0.1:8000/api/sample`（20GP + SKU-A/B/C，含承重上限）
- 排箱：`POST http://127.0.0.1:8000/api/pack`
- 导入 SKU：`POST http://127.0.0.1:8000/api/items/import`（`multipart` 字段名 `file`，`.xlsx` / `.xls` / `.csv`）
- 校验手动布局：`POST http://127.0.0.1:8000/api/pack/layout`（请求体在排箱字段外再带 `placements`；不合法返回 400）
- 导出装箱单：`POST http://127.0.0.1:8000/api/pack/export?format=xlsx`（或 `csv`、`pdf`）。若请求体带 `placements`，按该布局导出，不再重新搜索。

导入表头支持中英别名，例如 `SKU` / `货号`、`品名`、`长` / `宽` / `高`、`重量`、`数量`、`可旋转`、`承重`、`可承重`。必须能识别长宽高列；空文件、没有 SKU 行或解析失败返回 400。成功时返回 `{ "items": [...], "count": n }`。

导出请求体与 `/api/pack` 相同。服务端先排箱再生成文件，响应为附件下载。

```bash
curl -s -D - -o packing-list.xlsx \
  -H 'Content-Type: application/json' \
  -X POST 'http://127.0.0.1:8000/api/pack/export?format=xlsx' \
  --data @body.json
```

`format` 默认 `xlsx`。非法值（例如 `html`）返回 400。PDF 为横向 A4，内容与汇总、明细一致，使用系统黑体。

工作簿含两张表：

| 表 | 内容 |
|----|------|
| 装箱汇总 | 柜型、内尺寸、限重、外包装尺寸、外包装表面积、装箱紧密度%、重量利用率%、总重量、重心及是否在带内、已装/未装件数，以及按 SKU 汇总的订单数量、已装/未装数量和已装重量 |
| 装箱明细 | 每个物理箱一行 |

明细列：SKU、品名、数量（每行 1 件）、长/宽/高(mm)、重量(kg)、放置 X/Y/Z(mm)、旋转（`0°` 或 `90°`）、卸载顺序、装载顺序、装箱紧密度%、总重量(kg)、状态（已装入 / 未装入）。

已装入行的长宽高是**摆放后**的尺寸（若旋转则长宽对调）。未装入行没有坐标和装卸顺序。CSV 与明细列相同，编码为带 BOM 的 UTF-8，方便 Excel 直接打开中文。

开发依赖与测试（在 `backend/` 目录）：

```bash
pip install -r requirements-dev.txt
pytest
```

示例 body：

```json
{
  "container": {
    "name": "20GP",
    "length": 5898,
    "width": 2352,
    "height": 2393,
    "max_weight": 28200,
    "cog_band": 0.15
  },
  "items": [
    {
      "id": "SKU-A",
      "name": "纸箱A",
      "length": 600,
      "width": 400,
      "height": 400,
      "weight": 12,
      "qty": 20,
      "allow_rotate": true,
      "max_stack_load_kg": 60,
      "stackable": true,
      "unload_seq": 1
    }
  ]
}
```

尺寸单位：**毫米 (mm)**，重量：**千克 (kg)**。

排箱规则：

- 在柜内尺寸上限里尽量缩小外包装表面积，再比体积。件数大于 1 时，物理箱 id 为 `SKU#1`、`SKU#2`。
- 水平面可 90° 对调长宽。堆叠要求底面约 85% 被支撑，且下方箱子 `stackable` 为真。
- `max_stack_load_kg` 是该箱上方允许的总重量；不填时默认约为自身重量的 5 倍。新增的重量会沿支撑链继续传给更下层，任一层超限都放不下。超重、超限重或放不下的件进入 `unplaced`。
- `unload_seq` 越小越先卸。同一条宽度通道里，先卸的箱子必须整箱位于后卸箱子靠柜门的一侧；搜索时后卸的先放入柜底。留空则不参与这个约束。
- **装箱紧密度**是已装体积相对**紧凑外包装**体积，不是相对整柜体积。
- 重心按重量加权。`cog_band` 默认 `0.15`，表示相对外包装长、宽几何中心的 ±15% 软带；结果在 `stats.cog_ok`。
- 柜门在长度正方向（`door_axis: "x+"`）。`unload_order` 为 1 表示靠近柜门、先卸；`load_order` 为 1 表示远离柜门、先装。

`stats` 还包含外包装长宽高、表面积、体积与重量利用率、重心坐标。

## 前端

另开终端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。Vite 已把 `/api` 代理到 `8000`，也可设 `VITE_API_BASE=http://127.0.0.1:8000`。

操作：

1. 打开页面即带 **20GP 示例**（三个 SKU，含承重上限）。也可点「载入 20GP 示例」从 `GET /api/sample` 重新填入。
2. 在 SKU 表里改编码、品名、长宽高、重量、数量、承重上限、是否允许 90° 旋转，或增删行。也可「导入 Excel」（`.xlsx` / `.xls` / `.csv`）。
3. 「一键排箱」后，左侧显示外包装尺寸与表面积、装箱紧密度、重心、总重量、未放入件数；右侧 3D 预览。红点是重心。在空白处拖拽旋转视角，滚轮缩放。
4. **按住箱子拖动**，松手才落位。拖动中箱子跟着指针，并吸附到柜壁或其他箱子的边；高度落到脚下的支撑面或地面。松手后服务端重算承重链、重心、紧密度和装卸顺序。重叠、悬空、超承重或挡住先卸货物时，箱子回到原位并提示原因。表格改过还没重新排箱时，不能拖动。
5. 点选箱子后按 `R` 或「旋转 90°」，长宽对调并吸附到正交朝向，同样走上面的校验和重算。
6. 「下载装箱单 (.xlsx)」「下载 CSV」或「下载 PDF」在手动拖拽/旋转之后，按当前布局导出；若表格已改，则按表格重新排箱再下载。

## 当前范围

- 轴对齐箱子、可选 90° 平面旋转、柜型尺寸与限重
- 支撑面积与承重上限、重心软带、LIFO 装卸顺序
- 紧凑外包装尺寸、表面积、装箱紧密度、未放入列表
- 导出 Excel / CSV 装箱单（`POST /api/pack/export`）
- 导入 Excel / CSV SKU（`POST /api/items/import`）
- 按住拖动，松手后重算利用率与重心；90° 旋转吸附
- 多层承重沿支撑链传递；`unload_seq` 进入排箱搜索
- PDF 装箱单（`format=pdf`）

尚未做：任意角度旋转、拖拽时实时改装卸通道、把手动位置写回 SKU 数量。

下一步见 REPORT.md 中的「MVP 顺序」。

## License

研究用脚手架，按需自行补充许可证。
