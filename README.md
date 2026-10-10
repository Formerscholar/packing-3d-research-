# packing-3d-research

外贸装箱（Container Loading）3D 研究项目：自动排箱 API + React Three Fiber 只读预览。

详细调研见根目录 [REPORT.md](./REPORT.md)，一页摘要见 [docs/SUMMARY.md](./docs/SUMMARY.md)。

## 目录

```
packing-3d-research/
  REPORT.md          # 技术调研（必读）
  docs/SUMMARY.md
  backend/           # FastAPI + Extreme-Point / FFD 排箱
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
- 示例请求：`GET http://127.0.0.1:8000/api/sample`（20GP + SKU-A/B/C）
- 排箱：`POST http://127.0.0.1:8000/api/pack`
- 导出装箱单：`POST http://127.0.0.1:8000/api/pack/export?format=xlsx`（或 `format=csv`）

请求体与 `/api/pack` 相同。服务端先排箱再生成文件，响应为附件下载。

```bash
curl -s -D - -o packing-list.xlsx \
  -H 'Content-Type: application/json' \
  -X POST 'http://127.0.0.1:8000/api/pack/export?format=xlsx' \
  --data @body.json
```

`format` 默认 `xlsx`。非法值（例如 `pdf`）返回 400。

工作簿含两张表：

| 表 | 内容 |
|----|------|
| 装箱汇总 | 柜型、内尺寸、限重、体积利用率%、总重量(kg)、已装/未装件数，以及按 SKU 汇总的订单数量与已装数量 |
| 装箱明细 | 每个物理箱一行 |

明细列：SKU、品名、数量（每行 1 件）、长/宽/高(mm)、重量(kg)、放置 X/Y/Z(mm)、旋转（`0°` 或 `90°`）、柜体积利用率%、总重量(kg)、状态（已装入 / 未装入）。

已装入行的长宽高是**摆放后**的尺寸（若旋转则长宽对调）。未装入行没有坐标。CSV 与明细列相同，编码为带 BOM 的 UTF-8，方便 Excel 直接打开中文。

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
    "max_weight": 28200
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
      "allow_rotate": true
    }
  ]
}
```

尺寸单位：**毫米 (mm)**，重量：**千克 (kg)**。返回 `placements`（每个箱子的 xyz + 长宽高）和利用率统计。

## 前端

另开终端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173 。Vite 已把 `/api` 代理到 `8000`，也可设 `VITE_API_BASE=http://127.0.0.1:8000`。

操作：

1. 打开页面即带 **20GP 示例**（三个 SKU）。也可点「载入 20GP 示例」从 `GET /api/sample` 重新填入。
2. 在 SKU 表里改编码、品名、长宽高、重量、数量、是否允许 90° 旋转，或增删行。
3. 「一键排箱」后，左侧显示体积利用率、总重量、未放入件数；右侧 3D 只读预览（可拖拽旋转）。
4. 「下载装箱单 (.xlsx)」或「下载 CSV」会按当前表格再排一次箱，并下载装箱单。改过表格后若还没重新排箱，指标旁会提示 3D 仍是上一次结果；下载时会按当前表格重算并刷新预览。

## MVP 范围

- ✅ 轴对齐箱子、可选 90° 平面旋转、20GP 级柜型
- ✅ 体积/重量利用率、未放入列表
- ✅ 导出 Excel / CSV 装箱单（`POST /api/pack/export`）
- ❌ 尚未做：承重堆码、重心、LIFO 装卸、手动拖拽微调、Excel 导入

下一步见 REPORT.md 中的「MVP 顺序」。

## License

研究用脚手架，按需自行补充许可证。
