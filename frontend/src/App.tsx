import { Canvas } from "@react-three/fiber";
import { Edges, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import { useCallback, useMemo, useRef, useState } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import { downloadPackingList, fetchSample, importItems, pack } from "./api";
import type { ContainerIn, ItemIn, PackRequest, PackResponse, PlacementOut } from "./types";

/** mm → scene units (meters-ish, scaled down for camera comfort) */
const SCALE = 0.001;

const PALETTE = [
  "#60a5fa",
  "#34d399",
  "#fbbf24",
  "#f472b6",
  "#a78bfa",
  "#2dd4bf",
  "#fb923c",
  "#e879f9",
];

function colorFor(id: string): string {
  const base = id.split("#")[0];
  let h = 0;
  for (let i = 0; i < base.length; i++) h = (h * 31 + base.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(h) % PALETTE.length];
}

function ContainerWire({
  length,
  width,
  height,
}: {
  length: number;
  width: number;
  height: number;
}) {
  const L = length * SCALE;
  const W = width * SCALE;
  const H = height * SCALE;
  return (
    <mesh position={[L / 2, H / 2, W / 2]}>
      <boxGeometry args={[L, H, W]} />
      <meshBasicMaterial color="#64748b" wireframe transparent opacity={0.35} />
    </mesh>
  );
}

function BoxMesh({
  p,
  selected,
  onSelect,
  onDragEnd,
}: {
  p: PlacementOut;
  selected: boolean;
  onSelect: (id: string) => void;
  onDragEnd: (id: string, x: number, y: number, z: number) => void;
}) {
  const L = p.length * SCALE;
  const W = p.width * SCALE;
  const H = p.height * SCALE;
  const dragging = useRef(false);
  const planeY = useRef(p.z * SCALE);
  const cx = (p.x + p.length / 2) * SCALE;
  const cy = (p.z + p.height / 2) * SCALE;
  const cz = (p.y + p.width / 2) * SCALE;

  const onPointerDown = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    dragging.current = true;
    planeY.current = p.z * SCALE;
    onSelect(p.id);
  };
  const onPointerUp = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    if (!dragging.current) return;
    dragging.current = false;
    const hit = e.point;
    // Three: x,y(up),z  -> API x,z(height),y(width)
    const nx = Math.max(0, hit.x / SCALE - p.length / 2);
    const ny = Math.max(0, hit.z / SCALE - p.width / 2);
    const nz = Math.max(0, planeY.current / SCALE);
    onDragEnd(p.id, nx, ny, nz);
  };

  return (
    <mesh
      position={[cx, cy, cz]}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerMissed={() => undefined}
    >
      <boxGeometry args={[L, H, W]} />
      <meshStandardMaterial
        color={selected ? "#f8fafc" : colorFor(p.id)}
        metalness={0.1}
        roughness={0.55}
        emissive={selected ? "#38bdf8" : "#000000"}
        emissiveIntensity={selected ? 0.35 : 0}
      />
      <Edges threshold={15} color={selected ? "#38bdf8" : "#0f172a"} />
    </mesh>
  );
}

function CogMarker({ x, y, z }: { x: number; y: number; z: number }) {
  return (
    <mesh position={[x * SCALE, z * SCALE, y * SCALE]}>
      <sphereGeometry args={[0.08, 16, 16]} />
      <meshStandardMaterial color="#f43f5e" emissive="#f43f5e" emissiveIntensity={0.5} />
    </mesh>
  );
}

function Scene({
  result,
  selectedId,
  onSelect,
  onDragEnd,
}: {
  result: PackResponse | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDragEnd: (id: string, x: number, y: number, z: number) => void;
}) {
  const c = result?.container;
  const lookAt = useMemo(() => {
    if (!c) return [2.5, 1, 1] as [number, number, number];
    return [(c.length * SCALE) / 2, (c.height * SCALE) / 2, (c.width * SCALE) / 2] as [
      number,
      number,
      number,
    ];
  }, [c]);

  return (
    <Canvas shadows>
      <color attach="background" args={["#0f1419"]} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[8, 12, 6]} intensity={1.1} />
      <PerspectiveCamera makeDefault position={[9, 5, 7]} fov={45} />
      <OrbitControls target={lookAt} makeDefault />
      <gridHelper args={[12, 24, "#334155", "#1e293b"]} position={[0, 0, 0]} />
      {c && <ContainerWire length={c.length} width={c.width} height={c.height} />}
      {result?.placements.map((p) => (
        <BoxMesh
          key={p.id}
          p={p}
          selected={selectedId === p.id}
          onSelect={onSelect}
          onDragEnd={onDragEnd}
        />
      ))}
      {result?.stats?.cog_x_mm != null && (
        <CogMarker
          x={result.stats.cog_x_mm}
          y={result.stats.cog_y_mm ?? 0}
          z={result.stats.cog_z_mm ?? 0}
        />
      )}
    </Canvas>
  );
}

/** Same 20GP preset as GET /api/sample. */
const PRESET_20GP: ContainerIn = {
  name: "20GP",
  length: 5898,
  width: 2352,
  height: 2393,
  max_weight: 28200,
};

const PRESET_20GP_ITEMS: ItemIn[] = [
  {
    id: "SKU-A",
    name: "纸箱A 600x400x400",
    length: 600,
    width: 400,
    height: 400,
    weight: 12,
    qty: 24,
    allow_rotate: true,
    max_stack_load_kg: 60,
  },
  {
    id: "SKU-B",
    name: "纸箱B 800x600x500",
    length: 800,
    width: 600,
    height: 500,
    weight: 25,
    qty: 12,
    allow_rotate: true,
    max_stack_load_kg: 80,
  },
  {
    id: "SKU-C",
    name: "纸箱C 400x300x300",
    length: 400,
    width: 300,
    height: 300,
    weight: 8,
    qty: 30,
    allow_rotate: true,
    max_stack_load_kg: 40,
  },
];

function blankItem(n: number): ItemIn {
  return {
    id: `SKU-${n}`,
    name: "",
    length: 400,
    width: 300,
    height: 300,
    weight: 5,
    qty: 1,
    allow_rotate: true,
    max_stack_load_kg: 25,
    stackable: true,
  };
}

function validate(items: ItemIn[], container: ContainerIn): string | null {
  if (!(container.length > 0 && container.width > 0 && container.height > 0)) {
    return "柜内尺寸必须大于 0";
  }
  if (container.max_weight != null && !(container.max_weight >= 0)) {
    return "限重不能为负";
  }
  if (items.length === 0) return "请至少添加一个 SKU";
  const ids = new Set<string>();
  for (const it of items) {
    const id = it.id.trim();
    if (!id) return "SKU 不能为空";
    if (ids.has(id)) return `SKU 重复：${id}`;
    ids.add(id);
    if (!(it.length > 0 && it.width > 0 && it.height > 0)) return `${id} 尺寸必须大于 0`;
    if (!Number.isInteger(it.qty) || it.qty < 1) return `${id} 数量须为不小于 1 的整数`;
    if (it.weight < 0) return `${id} 重量不能为负`;
  }
  return null;
}

export default function App() {
  const [container, setContainer] = useState<ContainerIn>(PRESET_20GP);
  const [items, setItems] = useState<ItemIn[]>(PRESET_20GP_ITEMS);
  const [result, setResult] = useState<PackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const requestBody = useCallback((): PackRequest => {
    return {
      container: {
        ...container,
        name: container.name.trim() || "20GP",
        max_weight: container.max_weight ?? null,
      },
      items: items.map((it) => ({
        ...it,
        id: it.id.trim(),
        name: it.name?.trim() || it.id.trim(),
        allow_rotate: it.allow_rotate !== false,
        max_stack_load_kg: it.max_stack_load_kg ?? null,
        stackable: it.stackable !== false,
      })),
    };
  }, [container, items]);

  const runPack = useCallback(async (req?: PackRequest) => {
    const body = req ?? requestBody();
    const problem = validate(body.items, body.container);
    if (problem) {
      setError(problem);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await pack(body);
      setResult(res);
      setDirty(false);
      if (req) {
        setContainer(req.container);
        setItems(req.items);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [requestBody]);

  const loadPreset = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sample = await fetchSample();
      setContainer(sample.container);
      setItems(sample.items);
      setDirty(true);
      setResult(null);
    } catch {
      setContainer(PRESET_20GP);
      setItems(PRESET_20GP_ITEMS);
      setDirty(true);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const exportList = useCallback(async (format: "xlsx" | "csv") => {
    const body = requestBody();
    const problem = validate(body.items, body.container);
    if (problem) {
      setError(problem);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await pack(body);
      setResult(res);
      setDirty(false);
      await downloadPackingList(body, format);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [requestBody]);

  const patchItem = (index: number, patch: Partial<ItemIn>) => {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
    setDirty(true);
  };


  const onDragEnd = useCallback((id: string, x: number, y: number, z: number) => {
    setResult((prev) => {
      if (!prev) return prev;
      const placements = prev.placements.map((p) =>
        p.id === id ? { ...p, x, y, z } : p
      );
      // naive overlap reject
      const me = placements.find((p) => p.id === id)!;
      const overlap = placements.some((o) => {
        if (o.id === id) return false;
        return !(
          me.x + me.length <= o.x ||
          o.x + o.length <= me.x ||
          me.y + me.width <= o.y ||
          o.y + o.width <= me.y ||
          me.z + me.height <= o.z ||
          o.z + o.height <= me.z
        );
      });
      if (overlap) return prev;
      const c = prev.container;
      if (
        me.x < 0 ||
        me.y < 0 ||
        me.z < 0 ||
        me.x + me.length > c.length ||
        me.y + me.width > c.width ||
        me.z + me.height > c.height
      ) {
        return prev;
      }
      return { ...prev, placements };
    });
    setDirty(true);
  }, []);

  const onImportExcel = useCallback(async (file: File) => {
    setError(null);
    setLoading(true);
    try {
      const data = await importItems(file);
      setItems(data.items);
      setDirty(true);
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const stats = result?.stats;
  const utilPct = stats ? (stats.volume_utilization * 100).toFixed(1) : null;
  const packSize =
    stats?.pack_length_mm != null
      ? `${Math.round(stats.pack_length_mm)} × ${Math.round(stats.pack_width_mm ?? 0)} × ${Math.round(stats.pack_height_mm ?? 0)} mm`
      : null;
  const packSurf =
    stats?.pack_surface_m2 != null ? stats.pack_surface_m2.toFixed(3) : null;
  const weightPct =
    stats?.weight_utilization != null
      ? (stats.weight_utilization * 100).toFixed(1)
      : null;

  return (
    <div className="app">
      <aside className="panel">
        <h1>装箱 3D · MVP</h1>
        <p className="sub">Layer A：编辑 SKU → 紧凑排箱 · 承重/重心/LIFO · 可拖拽→ 下载装箱单</p>

        <section className="block">
          <div className="block-head">
            <h2>柜型</h2>
            <button type="button" className="ghost" onClick={loadPreset} disabled={loading}>
              载入 20GP 示例
            </button>
          </div>
          <div className="container-grid">
            <label>
              名称
              <input
                value={container.name}
                onChange={(e) => {
                  setContainer({ ...container, name: e.target.value });
                  setDirty(true);
                }}
              />
            </label>
            <label>
              长 mm
              <input
                type="number"
                min={1}
                value={container.length}
                onChange={(e) => {
                  setContainer({ ...container, length: Number(e.target.value) });
                  setDirty(true);
                }}
              />
            </label>
            <label>
              宽 mm
              <input
                type="number"
                min={1}
                value={container.width}
                onChange={(e) => {
                  setContainer({ ...container, width: Number(e.target.value) });
                  setDirty(true);
                }}
              />
            </label>
            <label>
              高 mm
              <input
                type="number"
                min={1}
                value={container.height}
                onChange={(e) => {
                  setContainer({ ...container, height: Number(e.target.value) });
                  setDirty(true);
                }}
              />
            </label>
            <label>
              限重 kg
              <input
                type="number"
                min={0}
                value={container.max_weight ?? ""}
                onChange={(e) => {
                  const raw = e.target.value;
                  setContainer({
                    ...container,
                    max_weight: raw === "" ? null : Number(raw),
                  });
                  setDirty(true);
                }}
              />
            </label>
          </div>
        </section>

        <div className="actions">
          <button type="button" onClick={() => runPack()} disabled={loading}>
            {loading ? "处理中…" : "一键排箱"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => exportList("xlsx")}
            disabled={loading}
          >
            下载装箱单 (.xlsx)
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => exportList("csv")}
            disabled={loading}
          >
            下载 CSV
          </button>
        </div>

        {error && <div className="error">{error}</div>}
        {dirty && result && (
          <div className="note">表格已修改，指标和 3D 仍是上一次排箱结果。</div>
        )}

        {stats && (
          <div className="metrics">
            <div className="metric">
              <span>外包装尺寸</span>
              <strong>{packSize ?? "—"}</strong>
            </div>
            <div className="metric">
              <span>外包装表面积</span>
              <strong>{packSurf != null ? `${packSurf} m²` : "—"}</strong>
            </div>
            <div className="metric">
              <span>装箱紧密度</span>
              <strong>{utilPct}%</strong>
              <small>
                {stats.volume_used_m3} / {stats.volume_total_m3} m³
              </small>
            </div>
            <div className="metric">
              <span>重心</span>
              <strong>
                {stats.cog_x_mm != null
                  ? `${Math.round(stats.cog_x_mm)}, ${Math.round(stats.cog_y_mm ?? 0)}, ${Math.round(stats.cog_z_mm ?? 0)}`
                  : "—"}
              </strong>
              <small>{stats.cog_ok === false ? "偏心，建议调整" : "在允许带内"}</small>
            </div>

            <div className="metric">
              <span>总重量</span>
              <strong>{stats.weight_used_kg} kg</strong>
              <small>
                {weightPct != null ? `限重的 ${weightPct}%` : "未设限重"}
                {stats.weight_limit_kg != null ? ` / ${stats.weight_limit_kg} kg` : ""}
              </small>
            </div>
            <div className="metric">
              <span>未放入</span>
              <strong>{stats.unplaced_count}</strong>
              <small>已放入 {stats.placed_count} 件</small>
            </div>
          </div>
        )}

        {result && result.unplaced.length > 0 && (
          <div className="unplaced">未放入：{result.unplaced.join(", ")}</div>
        )}

        <section className="block">
          <div className="block-head">
            <h2>SKU</h2>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setItems((prev) => [...prev, blankItem(prev.length + 1)]);
                  setDirty(true);
                }}
                disabled={loading}
              >
                添加一行
              </button>
              <label className="ghost" style={{ cursor: "pointer", padding: "4px 8px" }}>
                导入 Excel
                <input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  style={{ display: "none" }}
                  disabled={loading}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void onImportExcel(f);
                    e.target.value = "";
                  }}
                />
              </label>
            </div>
          </div>
          <div className="list">
            <table className="sku-edit">
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>品名</th>
                  <th>长</th>
                  <th>宽</th>
                  <th>高</th>
                  <th>kg</th>
                  <th>数量</th>
                  <th>承重kg</th>
                  <th>旋转</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, index) => (
                  <tr key={index}>
                    <td>
                      <input
                        aria-label={`SKU ${index + 1}`}
                        value={it.id}
                        onChange={(e) => patchItem(index, { id: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`品名 ${index + 1}`}
                        value={it.name ?? ""}
                        onChange={(e) => patchItem(index, { name: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`长 ${index + 1}`}
                        type="number"
                        min={1}
                        value={it.length}
                        onChange={(e) => patchItem(index, { length: Number(e.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`宽 ${index + 1}`}
                        type="number"
                        min={1}
                        value={it.width}
                        onChange={(e) => patchItem(index, { width: Number(e.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`高 ${index + 1}`}
                        type="number"
                        min={1}
                        value={it.height}
                        onChange={(e) => patchItem(index, { height: Number(e.target.value) })}
                      />
                    </td>
                    <td>
                      <input
                        aria-label={`重量 ${index + 1}`}
                        type="number"
                        min={0}
                        step="0.1"
                        value={it.weight}
                        onChange={(e) => patchItem(index, { weight: Number(e.target.value) })}
                      />
                    </td>
                                          <td>
                        <input
                          type="number"
                          min={0}
                          step={1}
                          value={it.max_stack_load_kg ?? ""}
                          onChange={(e) =>
                            patchItem(index, {
                              max_stack_load_kg:
                                e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                        />
                      </td>
                    <td>
                      <input
                        aria-label={`承重 ${index + 1}`}
                        type="number"
                        min={0}
                        step={1}
                        value={it.max_stack_load_kg ?? ""}
                        onChange={(e) =>
                          patchItem(index, {
                            max_stack_load_kg:
                              e.target.value === "" ? null : Number(e.target.value),
                          })
                        }
                      />
                    </td>
<td>
                      <input
                        aria-label={`数量 ${index + 1}`}
                        type="number"
                        min={1}
                        step={1}
                        value={it.qty}
                        onChange={(e) => patchItem(index, { qty: Number(e.target.value) })}
                      />
                    </td>
                    <td className="center">
                      <input
                        aria-label={`允许旋转 ${index + 1}`}
                        type="checkbox"
                        checked={it.allow_rotate !== false}
                        onChange={(e) => patchItem(index, { allow_rotate: e.target.checked })}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="ghost danger"
                        aria-label={`删除 ${it.id || index + 1}`}
                        onClick={() => {
                          setItems((prev) => prev.filter((_, i) => i !== index));
                          setDirty(true);
                        }}
                      >
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="unit-hint">尺寸单位 mm。旋转指水平面 90° 对调长宽。</p>
        </section>
      </aside>

      <main className="viewport">
        <div className="hint">拖拽旋转 · 滚轮缩放 · 单位 mm→m 显示</div>
        <Scene result={result} selectedId={selectedId} onSelect={setSelectedId} onDragEnd={onDragEnd} />
      </main>
    </div>
  );
}
