import { Canvas } from "@react-three/fiber";
import { Edges, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import { useCallback, useMemo, useState } from "react";
import { fetchSample, pack } from "./api";
import type { ItemIn, PackRequest, PackResponse, PlacementOut } from "./types";

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

function BoxMesh({ p }: { p: PlacementOut }) {
  const L = p.length * SCALE;
  const W = p.width * SCALE;
  const H = p.height * SCALE;
  // API: x along length, y along width, z along height
  // Three.js: x, y(up), z
  const cx = (p.x + p.length / 2) * SCALE;
  const cy = (p.z + p.height / 2) * SCALE;
  const cz = (p.y + p.width / 2) * SCALE;
  return (
    <mesh position={[cx, cy, cz]}>
      <boxGeometry args={[L, H, W]} />
      <meshStandardMaterial color={colorFor(p.id)} metalness={0.1} roughness={0.55} />
      <Edges threshold={15} color="#0f172a" />
    </mesh>
  );
}

function Scene({ result }: { result: PackResponse | null }) {
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
        <BoxMesh key={p.id} p={p} />
      ))}
    </Canvas>
  );
}

const DEFAULT_ITEMS: ItemIn[] = [
  {
    id: "SKU-A",
    name: "纸箱A 600x400x400",
    length: 600,
    width: 400,
    height: 400,
    weight: 12,
    qty: 20,
  },
  {
    id: "SKU-B",
    name: "纸箱B 800x600x500",
    length: 800,
    width: 600,
    height: 500,
    weight: 25,
    qty: 8,
  },
  {
    id: "SKU-C",
    name: "纸箱C 400x300x300",
    length: 400,
    width: 300,
    height: 300,
    weight: 8,
    qty: 15,
  },
];

export default function App() {
  const [items, setItems] = useState<ItemIn[]>(DEFAULT_ITEMS);
  const [result, setResult] = useState<PackResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runPack = useCallback(async (req?: PackRequest) => {
    setLoading(true);
    setError(null);
    try {
      const body: PackRequest =
        req ??
        ({
          container: {
            name: "20GP",
            length: 5898,
            width: 2352,
            height: 2393,
            max_weight: 28200,
          },
          items,
        } as PackRequest);
      const res = await pack(body);
      setResult(res);
      if (req?.items) setItems(req.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [items]);

  const loadSample = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const sample = await fetchSample();
      setItems(sample.items);
      const res = await pack(sample);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  const stats = result?.stats;

  return (
    <div className="app">
      <aside className="panel">
        <h1>装箱 3D · MVP</h1>
        <p className="sub">Layer A：录入 → 一键排箱 → 3D 只读预览</p>

        <button type="button" onClick={() => runPack()} disabled={loading}>
          {loading ? "计算中…" : "一键排箱（当前 SKU）"}
        </button>
        <button
          type="button"
          className="secondary"
          onClick={loadSample}
          disabled={loading}
        >
          加载示例并排箱
        </button>

        {error && <div className="error">{error}</div>}

        {stats && (
          <div className="stats">
            <div>
              已放入 <strong>{stats.placed_count}</strong> / 未放入{" "}
              <strong>{stats.unplaced_count}</strong>
            </div>
            <div>
              体积利用率{" "}
              <strong>{(stats.volume_utilization * 100).toFixed(1)}%</strong>（
              {stats.volume_used_m3} / {stats.volume_total_m3} m³）
            </div>
            <div>
              重量 <strong>{stats.weight_used_kg} kg</strong>
              {stats.weight_utilization != null &&
                `（${(stats.weight_utilization * 100).toFixed(1)}%）`}
            </div>
          </div>
        )}

        <div className="list">
          <table>
            <thead>
              <tr>
                <th>SKU</th>
                <th>尺寸 mm</th>
                <th>数量</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => (
                <tr key={it.id}>
                  <td>{it.name ?? it.id}</td>
                  <td>
                    {it.length}×{it.width}×{it.height}
                  </td>
                  <td>{it.qty}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {result && result.unplaced.length > 0 && (
          <div className="stats" style={{ marginTop: 8 }}>
            未放入：{result.unplaced.join(", ")}
          </div>
        )}
      </aside>

      <main className="viewport">
        <div className="hint">拖拽旋转 · 滚轮缩放 · 单位 mm→m 显示</div>
        <Scene result={result} />
      </main>
    </div>
  );
}
