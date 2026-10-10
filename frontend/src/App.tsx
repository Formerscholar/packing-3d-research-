import { Canvas, useThree } from "@react-three/fiber";
import { Edges, OrbitControls, PerspectiveCamera } from "@react-three/drei";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import type { ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import { downloadPackingList, fetchSample, importItems, pack, submitLayout } from "./api";
import { dropZ, separateOnFloor, snapXY, sourceItem } from "./placement";
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
  onPointerDown,
}: {
  p: PlacementOut;
  selected: boolean;
  onPointerDown: (event: ThreeEvent<PointerEvent>, placement: PlacementOut) => void;
}) {
  const L = p.length * SCALE;
  const W = p.width * SCALE;
  const H = p.height * SCALE;
  const cx = (p.x + p.length / 2) * SCALE;
  const cy = (p.z + p.height / 2) * SCALE;
  const cz = (p.y + p.width / 2) * SCALE;

  return (
    <mesh
      position={[cx, cy, cz]}
      onPointerDown={(event) => onPointerDown(event, p)}
      onPointerOver={(event) => {
        event.stopPropagation();
        document.body.style.cursor = "grab";
      }}
      onPointerOut={() => {
        if (document.body.style.cursor === "grab") document.body.style.cursor = "";
      }}
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

type DragSession = {
  id: string;
  originX: number;
  originY: number;
  grabApiX: number;
  grabApiY: number;
  planeY: number;
  snapshot: PlacementOut[];
  moved: boolean;
};

function clientToApi(
  clientX: number,
  clientY: number,
  planeY: number,
  gl: THREE.WebGLRenderer,
  camera: THREE.Camera
): { apiX: number; apiY: number } | null {
  const rect = gl.domElement.getBoundingClientRect();
  const ndcX = ((clientX - rect.left) / rect.width) * 2 - 1;
  const ndcY = -((clientY - rect.top) / rect.height) * 2 + 1;
  const raycaster = new THREE.Raycaster();
  raycaster.setFromCamera(new THREE.Vector2(ndcX, ndcY), camera);
  const direction = raycaster.ray.direction;
  if (Math.abs(direction.y) < 1e-6) return null;
  const distance = (planeY - raycaster.ray.origin.y) / direction.y;
  if (distance < 0) return null;
  return {
    apiX: (raycaster.ray.origin.x + direction.x * distance) / SCALE,
    apiY: (raycaster.ray.origin.z + direction.z * distance) / SCALE,
  };
}

function PointerDrag({
  session,
  containerRef,
  onPreview,
  onEnd,
}: {
  session: MutableRefObject<DragSession | null>;
  containerRef: MutableRefObject<ContainerIn | null>;
  onPreview: (next: PlacementOut[]) => void;
  onEnd: (finished: DragSession) => void;
}) {
  const { gl, camera } = useThree();
  const previewRef = useRef(onPreview);
  const endRef = useRef(onEnd);
  previewRef.current = onPreview;
  endRef.current = onEnd;

  useEffect(() => {
    const element = gl.domElement;
    const onMove = (event: PointerEvent) => {
      const current = session.current;
      const container = containerRef.current;
      if (!current || !container || event.buttons !== 1) return;
      const hit = clientToApi(event.clientX, event.clientY, current.planeY, gl, camera);
      if (!hit) return;
      const me = current.snapshot.find((item) => item.id === current.id);
      if (!me) return;
      const rawX = Math.max(
        0,
        Math.min(current.originX + (hit.apiX - current.grabApiX), container.length - me.length)
      );
      const rawY = Math.max(
        0,
        Math.min(current.originY + (hit.apiY - current.grabApiY), container.width - me.width)
      );
      const others = current.snapshot.filter((item) => item.id !== current.id);
      const snapped = snapXY(rawX, rawY, me.length, me.width, others, container);
      const z = dropZ(
        snapped.x,
        snapped.y,
        me.length,
        me.width,
        me.height,
        others,
        container.height
      );
      if (z == null) return;
      if (
        Math.abs(snapped.x - current.originX) > 2 ||
        Math.abs(snapped.y - current.originY) > 2 ||
        Math.abs(z - me.z) > 2
      ) {
        current.moved = true;
      }
      previewRef.current(
        current.snapshot.map((item) =>
          item.id === current.id ? { ...me, x: snapped.x, y: snapped.y, z } : item
        )
      );
    };
    const onUp = () => {
      const current = session.current;
      if (!current) return;
      session.current = null;
      document.body.style.cursor = "";
      endRef.current(current);
    };
    element.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      element.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [camera, containerRef, gl, session]);

  return null;
}

function Scene({
  result,
  selectedId,
  dragEnabled,
  onSelect,
  onCommit,
}: {
  result: PackResponse | null;
  selectedId: string | null;
  dragEnabled: boolean;
  onSelect: (id: string) => void;
  onCommit: (placements: PlacementOut[]) => Promise<string | null>;
}) {
  const controls = useRef<{ enabled: boolean } | null>(null);
  const session = useRef<DragSession | null>(null);
  const [live, setLive] = useState<PlacementOut[] | null>(null);
  const [orbitOn, setOrbitOn] = useState(true);
  const liveRef = useRef<PlacementOut[] | null>(null);
  const containerRef = useRef<ContainerIn | null>(result?.container ?? null);
  containerRef.current = result?.container ?? null;
  const c = result?.container;
  const placements = live ?? result?.placements ?? [];

  useEffect(() => {
    setLive(null);
    liveRef.current = null;
  }, [result]);

  const lookAt = useMemo(() => {
    if (!c) return [2.5, 1, 1] as [number, number, number];
    return [(c.length * SCALE) / 2, (c.height * SCALE) / 2, (c.width * SCALE) / 2] as [
      number,
      number,
      number,
    ];
  }, [c]);

  const beginDrag = (event: ThreeEvent<PointerEvent>, placement: PlacementOut) => {
    event.stopPropagation();
    event.nativeEvent.stopPropagation();
    onSelect(placement.id);
    if (!dragEnabled || !result) return;
    if (controls.current) controls.current.enabled = false;
    setOrbitOn(false);
    document.body.style.cursor = "grabbing";
    session.current = {
      id: placement.id,
      originX: placement.x,
      originY: placement.y,
      grabApiX: event.point.x / SCALE,
      grabApiY: event.point.z / SCALE,
      planeY: event.point.y,
      snapshot: (live ?? result.placements).map((item) => ({ ...item })),
      moved: false,
    };
  };

  const finishDrag = (finished: DragSession) => {
    setOrbitOn(true);
    if (controls.current) controls.current.enabled = true;
    if (!finished.moved) {
      setLive(null);
      liveRef.current = null;
      return;
    }
    const next = liveRef.current;
    if (!next) return;
    void onCommit(next).then((err) => {
      if (err) {
        setLive(null);
        liveRef.current = null;
      }
    });
  };

  return (
    <Canvas shadows role="application" aria-label="三维预览">
      <color attach="background" args={["#0f1419"]} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[8, 12, 6]} intensity={1.1} />
      <PerspectiveCamera makeDefault position={[9, 5, 7]} fov={45} />
      <OrbitControls ref={controls as never} target={lookAt} makeDefault enabled={orbitOn} />
      <PointerDrag
        session={session}
        containerRef={containerRef}
        onPreview={(next) => {
          liveRef.current = next;
          setLive(next);
        }}
        onEnd={finishDrag}
      />
      <gridHelper args={[12, 24, "#334155", "#1e293b"]} position={[0, 0, 0]} />
      {c && <ContainerWire length={c.length} width={c.width} height={c.height} />}
      {placements.map((p) => (
        <BoxMesh
          key={p.id}
          p={p}
          selected={selectedId === p.id}
          onPointerDown={beginDrag}
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
  const [manualLayout, setManualLayout] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const markEdited = () => {
    setDirty(true);
    setManualLayout(false);
  };

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
        unload_seq: it.unload_seq ?? null,
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
      setSelectedId(res.placements[0]?.id ?? null);
      setManualLayout(false);
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
      setManualLayout(false);
      setResult(null);
      setSelectedId(null);
    } catch {
      setContainer(PRESET_20GP);
      setItems(PRESET_20GP_ITEMS);
      setDirty(true);
      setManualLayout(false);
      setResult(null);
      setSelectedId(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const exportList = useCallback(async (format: "xlsx" | "csv" | "pdf") => {
    const body = requestBody();
    const problem = validate(body.items, body.container);
    if (problem) {
      setError(problem);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (manualLayout && result && !dirty) {
        await downloadPackingList({ ...body, placements: result.placements }, format);
      } else {
        const res = await pack(body);
        setResult(res);
        setSelectedId(res.placements[0]?.id ?? null);
        setManualLayout(false);
        setDirty(false);
        await downloadPackingList(body, format);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [dirty, manualLayout, requestBody, result]);

  const patchItem = (index: number, patch: Partial<ItemIn>) => {
    setItems((prev) => prev.map((it, i) => (i === index ? { ...it, ...patch } : it)));
    markEdited();
  };

  const commitLayout = useCallback(async (placements: PlacementOut[]): Promise<string | null> => {
    const body = requestBody();
    const problem = validate(body.items, body.container);
    if (problem) {
      setError(problem);
      return problem;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await submitLayout({ ...body, placements });
      setResult(res);
      setManualLayout(true);
      setDirty(false);
      return null;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      return message;
    } finally {
      setLoading(false);
    }
  }, [requestBody]);

  const rotateSelected = useCallback(async () => {
    if (!result || !selectedId) {
      setError("先点选一个箱子");
      return;
    }
    if (dirty) {
      setError("表格已改，请先重新排箱再旋转");
      return;
    }
    const body = requestBody();
    const target = result.placements.find((item) => item.id === selectedId);
    if (!target) return;
    const src = sourceItem(target.id, body.items);
    if (src && src.allow_rotate === false) {
      setError("该 SKU 不允许旋转");
      return;
    }
    const others = result.placements.filter((item) => item.id !== target.id);
    const swapped: PlacementOut = {
      ...target,
      length: target.width,
      width: target.length,
      rotated: !target.rotated,
    };
    const snapped = snapXY(
      swapped.x,
      swapped.y,
      swapped.length,
      swapped.width,
      others,
      result.container
    );
    const separated =
      separateOnFloor(
        snapped.x,
        snapped.y,
        swapped.length,
        swapped.width,
        swapped.height,
        others,
        result.container
      ) ?? {
        x: Math.max(0, Math.min(snapped.x, result.container.length - swapped.length)),
        y: Math.max(0, Math.min(snapped.y, result.container.width - swapped.width)),
      };
    const pose: PlacementOut = {
      ...swapped,
      x: separated.x,
      y: separated.y,
    };
    const z = dropZ(
      pose.x,
      pose.y,
      pose.length,
      pose.width,
      pose.height,
      others,
      result.container.height
    );
    if (z == null) {
      setError("旋转后放不进柜子");
      return;
    }
    await commitLayout(result.placements.map((item) => (item.id === target.id ? { ...pose, z } : item)));
  }, [commitLayout, dirty, requestBody, result, selectedId]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "r" && event.key !== "R") return;
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      event.preventDefault();
      void rotateSelected();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rotateSelected]);

  const onImportExcel = useCallback(async (file: File) => {
    setError(null);
    setLoading(true);
    try {
      const data = await importItems(file);
      setItems(data.items);
      setDirty(true);
      setManualLayout(false);
      setResult(null);
      setSelectedId(null);
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
        <p className="sub">按住箱子拖动，松手后重算重心和紧密度。R 或「旋转 90°」只吸附到正交朝向。</p>

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
                  markEdited();
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
                  markEdited();
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
                  markEdited();
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
                  markEdited();
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
                  markEdited();
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
          <button
            type="button"
            className="secondary"
            onClick={() => exportList("pdf")}
            disabled={loading}
          >
            下载 PDF
          </button>
        </div>

        {error && <div className="error">{error}</div>}
        {dirty && result && (
          <div className="note">表格已修改，指标和 3D 仍是上一次排箱结果。请先重新排箱再拖动。</div>
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
                  markEdited();
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
                  <th>卸序</th>
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
                        aria-label={`数量 ${index + 1}`}
                        type="number"
                        min={1}
                        step={1}
                        value={it.qty}
                        onChange={(e) => patchItem(index, { qty: Number(e.target.value) })}
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
                        aria-label={`卸序 ${index + 1}`}
                        type="number"
                        min={1}
                        step={1}
                        value={it.unload_seq ?? ""}
                        onChange={(e) =>
                          patchItem(index, {
                            unload_seq: e.target.value === "" ? null : Number(e.target.value),
                          })
                        }
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
                          markEdited();
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
          <p className="unit-hint">尺寸单位 mm。旋转指水平面 90°。卸序越小越先卸，并靠近柜门。</p>
        </section>
      </aside>

      <main className="viewport">
        <div className="hint">
          按住箱子拖动，靠近箱边或柜壁会吸附。松手后重算重心和紧密度。滚轮缩放视角。
          {selectedId && result?.placements.find((item) => item.id === selectedId) && (
            <span>
              选中 {selectedId} @{" "}
              {Math.round(result.placements.find((item) => item.id === selectedId)!.x)},{" "}
              {Math.round(result.placements.find((item) => item.id === selectedId)!.y)},{" "}
              {Math.round(result.placements.find((item) => item.id === selectedId)!.z)}
              {result.placements.find((item) => item.id === selectedId)!.rotated ? " · 90°" : " · 0°"}
            </span>
          )}
          <button type="button" onClick={() => void rotateSelected()} disabled={!selectedId || loading || dirty}>
            旋转 90°
          </button>
        </div>
        <Scene
          result={result}
          selectedId={selectedId}
          dragEnabled={!dirty && !loading}
          onSelect={setSelectedId}
          onCommit={commitLayout}
        />
      </main>
    </div>
  );
}
