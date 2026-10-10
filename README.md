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
- 示例请求：`GET http://127.0.0.1:8000/api/sample`
- 排箱：`POST http://127.0.0.1:8000/api/pack`

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

操作：点「加载示例并排箱」或「一键排箱」，左侧看利用率，右侧 3D 只读预览（可拖拽旋转）。

## MVP 范围

- ✅ 轴对齐箱子、可选 90° 平面旋转、20GP 级柜型
- ✅ 体积/重量利用率
- ❌ 尚未做：承重堆码、重心、LIFO 装卸、手动拖拽微调、导出装箱单

下一步见 REPORT.md 中的「MVP 顺序」。

## License

研究用脚手架，按需自行补充许可证。
