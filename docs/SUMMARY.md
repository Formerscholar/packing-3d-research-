# 一页摘要：外贸装箱 3D

**痛点**：柜内空间难算；要自动排箱 + 手动 3D 微调 + 导出装箱数据。自研常卡在技术栈，3D 达不到「普通人可用」。

**问题本质**：做的是 **Container Loading（固定柜型 + 多约束）**，不是裸的 3D bin packing。先建模柜型/重量/朝向/堆码/装卸顺序/重心/单据字段，再谈可视化。

**UX 顺序（别跳级）**
1. **Layer A**：SKU 录入 → 自动排 → 列表 + 俯视/分层 + 指标  
2. **Layer B**：完整 3D 拖拽/旋转/吸附  
失败主因：引擎未稳就上 Unity 级 3D。

**算法**：MVP 用 **Extreme Point + 分层/FFD**；GA/SA 二期做多目标微调。`py3dbp` 适合原型（宜 fork）；OR-Tools 只适合小实例；**别用 LLM 算几何**。AI 最多做偏好排序。

**3D 前端**：浏览器 **React Three Fiber + drei + TransformControls**；碰撞先 **AABB**，再考虑 rapier。避免 raw OpenGL / 过早 Unity。

**架构**：后端引擎出 `placements JSON`；前端只渲染与编辑；拖完校验碰撞并重算利用率/重量/顺序；导出 Excel/PDF 装箱单。

**主推栈**：Python（fork/自研 EP）+ FastAPI + React/R3F/drei；备选 Go 引擎或 EasyCargo 仅作展示层。

**MVP（4–8 周）**：引擎可回归 → Layer A → 导出 → 再 Layer B。先单据与利用率，后炫技。

**给摔过一次的你**：3D 是放大器；**排箱引擎 + 装箱单**才是产品。先 4 周引擎与 Excel，再用 R3F 接 placements。
