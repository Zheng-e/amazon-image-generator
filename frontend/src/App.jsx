import {
  Check,
  Database,
  FileImage,
  Plus,
  Search,
  Sparkles,
  Star,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

const API = import.meta.env.VITE_API_BASE || window.location.origin;

const ASSET_TYPE_LABELS = {
  product: "商品",
  model: "模特",
  competitor: "竞品",
};

const RAG_USAGE_TAGS = [
  ["scene_reference", "场景参考"],
  ["pose_reference", "姿势参考"],
  ["composition_reference", "构图参考"],
  ["color_reference", "色调参考"],
  ["white_main_reference", "白底主图参考"],
  ["competitor_fit_reference", "竞品上身参考"],
];

function defaultRagQuery(project) {
  return [project?.category, project?.name, project?.sku, "服装 主图 场景 构图 光影"]
    .filter(Boolean)
    .join(" ");
}

function ImagePreviewModal({ src, alt, onClose }) {
  if (!src) return null;
  return (
    <div className="image-preview-overlay" onClick={onClose}>
      <div className="image-preview-content" onClick={(e) => e.stopPropagation()}>
        <button className="image-preview-close" onClick={onClose}>
          <X size={20} />
        </button>
        <img src={src} alt={alt || ""} />
      </div>
    </div>
  );
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function docxRunReadyToDownload(wf) {
  const steps = wf?.steps || [];
  return steps.length === 9 && steps.every((step) => step.status === "success" && (step.url || step.image_path));
}

function WorkflowStatusBadge({ project }) {
  const status = project.workflow_status || "idle";
  const labels = { idle: "待开始", running: "生成中", partial: "部分完成", success: "已完成", failed: "失败" };
  if (project.has_downloads) {
    return <span className="workflow-badge downloaded">已下载</span>;
  }
  return <span className={`workflow-badge ${status}`}>{labels[status] || status}</span>;
}

function StepProgress({ project }) {
  const summary = project.step_summary;
  if (!summary || summary.total === 0) return null;
  return <small className="step-progress">{summary.success}/{summary.total} 张已完成</small>;
}

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

const RAG_ASSET_TYPES = [
  ["", "全部类型"],
  ["model", "模特图"],
  ["other", "其他参考图"],
];

const RAG_ASSET_TYPE_LABELS = { model: "模特图", other: "其他参考图" };

const RAG_ROLES = [
  ["", "未指定"],
  ["model", "模特参考"],
  ["scene_style", "场景风格参考"],
  ["pose", "姿势参考"],
  ["accessory", "配饰参考"],
];

const RAG_ROLE_LABELS = { model: "模特参考", scene_style: "场景风格参考", pose: "姿势参考", accessory: "配饰参考" };

const RAG_USE_ROLES = [
  { rag_role: "model", slot: "model_reference", label: "用作模特参考" },
  { rag_role: "scene_style", slot: "scene_reference", label: "用作场景风格参考" },
  { rag_role: "pose", slot: "pose_reference", label: "用作姿势参考" },
  { rag_role: "accessory", slot: "accessory_reference", label: "用作配饰参考" },
];
const RAG_SEARCH_CACHE_LIMIT = 200;

function RagSearchPanel({ title, assetType, defaultQuery, busy, onUseAsAsset }) {
  const [query, setQuery] = useState(defaultQuery || "");
  const [topK, setTopK] = useState(8);
  const [results, setResults] = useState([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [error, setError] = useState("");
  const [previewImage, setPreviewImage] = useState(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [cachedResults, setCachedResults] = useState([]);
  const [cacheHasMore, setCacheHasMore] = useState(false);
  const [searchCache, setSearchCache] = useState({});

  const showCachedPage = (items, nextPage, pageSize = topK) => {
    const safePageSize = Math.max(1, Number(pageSize) || 8);
    const maxPage = Math.max(0, Math.ceil(items.length / safePageSize) - 1);
    const safePage = Math.min(Math.max(0, nextPage), maxPage);
    const start = safePage * safePageSize;
    setPage(safePage);
    setResults(items.slice(start, start + safePageSize));
    setHasMore(start + safePageSize < items.length);
  };

  const doSearch = async () => {
    if (!query.trim()) return;
    const filters = assetType ? { asset_type: assetType } : {};
    const cacheKey = JSON.stringify({ query: query.trim(), filters });
    const cached = searchCache[cacheKey];
    if (cached) {
      setCachedResults(cached.results);
      setCacheHasMore(cached.hasMore);
      showCachedPage(cached.results, 0);
      return;
    }
    setSearchBusy(true);
    setError("");
    try {
      const fetchLimit = Math.max(RAG_SEARCH_CACHE_LIMIT, Number(topK) || 8);
      const data = await request("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query, top_k: fetchLimit, offset: 0, filters }),
      });
      const nextResults = data.results || [];
      setCachedResults(nextResults);
      setCacheHasMore(Boolean(data.has_more));
      setSearchCache((prev) => ({
        ...prev,
        [cacheKey]: { results: nextResults, hasMore: Boolean(data.has_more) },
      }));
      showCachedPage(nextResults, 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setSearchBusy(false);
    }
  };

  const prevPage = () => {
    if (page <= 0) return;
    showCachedPage(cachedResults, page - 1);
  };

  const nextPage = () => {
    if (!hasMore) return;
    showCachedPage(cachedResults, page + 1);
  };

  return (
    <div className="rag-search-panel">
      <div className="rag-panel-head">
        <strong>{title}</strong>
      </div>
      <div className="rag-panel-controls">
        <label className="stacked-field">
          <span>检索词</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} />
        </label>
        <label className="stacked-field narrow">
          <span>数量</span>
          <input
            type="number"
            min="1"
            max="64"
            value={topK}
            onChange={(event) => {
              const nextTopK = Number(event.target.value) || 8;
              setTopK(nextTopK);
              if (cachedResults.length) {
                showCachedPage(cachedResults, 0, nextTopK);
              }
            }}
          />
        </label>
        <button className="primary" disabled={searchBusy || !query.trim() || busy} onClick={() => doSearch()}>
          <Search size={14} />
          搜索
        </button>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      {results.length ? (
        <div className="rag-pagination">
          <button disabled={page <= 0 || searchBusy} onClick={prevPage}>上一页</button>
          <span>第 {page + 1} / {Math.max(1, Math.ceil(cachedResults.length / topK))} 页</span>
          <button disabled={!hasMore || searchBusy} onClick={nextPage}>下一页</button>
          <small>已缓存 {cachedResults.length} 张{cacheHasMore ? "，后续结果可重新搜索刷新" : ""}</small>
        </div>
      ) : null}
      <div className="rag-results-grid">
        {results.map((item) => (
          <article key={item.image_id} className="rag-card">
            <img
              src={`${API}/api/rag/images/${item.image_id}`}
              alt={item.filename || item.image_id}
              className="clickable-img"
              onClick={() => setPreviewImage({ src: `${API}/api/rag/images/${item.image_id}`, alt: item.filename || item.image_id })}
            />
            <div className="rag-card-body">
              <strong>{item.filename || item.image_id}</strong>
              <span>{item.category || "未分类"} · {item.scene || "未知场景"}</span>
              <small>{item.image_type || item.caption || ""}</small>
              <em>相似度：{typeof item.score === "number" ? item.score.toFixed(4) : "-"}</em>
              <div className="rag-use-buttons">
                {RAG_USE_ROLES.filter((r) => assetType === "model" ? r.rag_role === "model" : r.rag_role !== "model").map((r) => (
                  <button key={r.rag_role} disabled={searchBusy || busy} onClick={() => onUseAsAsset(item, r)}>
                    <Check size={12} />
                    {r.label}
                  </button>
                ))}
              </div>
            </div>
          </article>
        ))}
        {!results.length && !searchBusy ? <p className="muted">输入检索词后点击搜索</p> : null}
      </div>
      <ImagePreviewModal src={previewImage?.src} alt={previewImage?.alt} onClose={() => setPreviewImage(null)} />
    </div>
  );
}

function RagKnowledgeWorkbench({ project, refreshProject, onAssetCreated }) {
  const [health, setHealth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const defaultQuery = defaultRagQuery(project);

  useEffect(() => {
    setError("");
    request("/api/rag/health").then(setHealth).catch((err) => setHealth({ status: "unavailable", detail: err.message }));
  }, [project?.id]);

  const useAsAsset = async (item, role) => {
    setBusy(true);
    setError("");
    try {
      const result = await request(`/api/projects/${project.id}/rag-to-asset`, {
        method: "POST",
        body: JSON.stringify({
          rag_image_id: item.image_id,
          filename: item.filename || "",
          slot: role.slot,
          rag_role: role.rag_role,
        }),
      });
      await refreshProject();
      if (onAssetCreated) onAssetCreated(result, role.slot);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel rag-workbench">
      <div className="section-title">
        <Database size={18} />
        <h2>知识库工作台</h2>
      </div>
      <div className="rag-status">
        <span className={health?.status === "ok" ? "status-ok" : "status-fail"}>
          RAG：{health?.status === "ok" ? `可用 · ${health.images || 0} 张图` : "不可用"}
        </span>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="rag-search-split">
        <RagSearchPanel title="模特图" assetType="model" defaultQuery={defaultQuery} busy={busy} onUseAsAsset={useAsAsset} />
        <RagSearchPanel title="场景 / 姿势 / 配饰参考图" assetType="other" defaultQuery={defaultQuery} busy={busy} onUseAsAsset={useAsAsset} />
      </div>
    </section>
  );
}

const DOCX_SLOT_TYPES = {
  product_image: ["product"],
  model_reference: ["model"],
  scene_reference: ["model", "competitor", "other"],
  fit_reference: ["competitor"],
  pose_reference: ["other"],
  accessory_reference: ["competitor", "other"],
};

const DOCX_SLOT_LABELS = {
  product_image: "产品图",
  model_reference: "模特参考图",
  scene_reference: "场景风格参考图",
  fit_reference: "上身效果参考",
  pose_reference: "姿势参考",
  accessory_reference: "配饰参考",
};

function docxAssetsForSlot(assets, slotHint) {
  const allowedTypes = DOCX_SLOT_TYPES[slotHint] || ["product", "model", "competitor"];
  const typedAssets = assets.filter((asset) => asset.url && allowedTypes.includes(asset.asset_type));
  const slotMatched = typedAssets.filter((asset) => asset.slot === slotHint);
  const fallback = typedAssets.filter((asset) => !asset.slot);
  return (slotMatched.length ? slotMatched : fallback).sort((a, b) =>
    String(b.created_at || "").localeCompare(String(a.created_at || ""))
  );
}

function DocxAssetSelect({ label, assets, slotHint, value, onChange }) {
  const visibleAssets = docxAssetsForSlot(assets, slotHint);
  const selected = assets.find((asset) => asset.id === value);
  return (
    <label className="docx-selector">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">请选择</option>
        {visibleAssets.map((asset) => (
          <option key={asset.id} value={asset.id}>
            [{ASSET_TYPE_LABELS[asset.asset_type] || asset.asset_type}] {asset.original_name}
            {asset.slot ? ` · ${DOCX_SLOT_LABELS[asset.slot] || asset.slot}` : ""}
          </option>
        ))}
      </select>
      {selected ? (
        <figure className="selected-ref">
          <img src={`${API}${selected.url}`} alt={selected.original_name} />
          <figcaption title={selected.original_name}>{selected.original_name}</figcaption>
        </figure>
      ) : null}
    </label>
  );
}

function DocxWorkflowPanel({ project, assets, refresh, onDownload, formSetterRef }) {
  const [styles, setStyles] = useState([]);
  const [imageModels, setImageModels] = useState([]);
  const [form, setForm] = useState({
    product_name: "",
    material: "",
    style_key: "natural_fashion",
    image_model: "gpt-image-2-client",
    size: "1024x1024",
    quality: "high",
    product_asset_id: "",
    model_asset_id: "",
    scene_asset_id: "",
    fit_front_asset_id: "",
    fit_side_asset_id: "",
    fit_back_asset_id: "",
    accessory_asset_id: "",
  });
  const [workflow, setWorkflow] = useState(null);
  const [promptDrafts, setPromptDrafts] = useState({});
  const [busy, setBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const productFileRef = useRef(null);
  const fitFrontFileRef = useRef(null);
  const fitSideFileRef = useRef(null);
  const fitBackFileRef = useRef(null);
  useEffect(() => {
    if (formSetterRef) formSetterRef.current = setForm;
    return () => { if (formSetterRef) formSetterRef.current = null; };
  }, [formSetterRef]);

  useEffect(() => {
    request("/api/docx-workflow/styles").then(setStyles).catch(() => setStyles([]));
    request("/api/models/image").then((models) => {
      setImageModels(models);
      setForm((current) => current.image_model ? current : { ...current, image_model: models[0]?.model || "gpt-image-2-client" });
    }).catch(() => setImageModels([]));
  }, []);

  useEffect(() => {
    setWorkflow(null);
    request(`/api/projects/${project.id}/workflow`)
      .then(setWorkflow)
      .catch(() => setWorkflow(null));
  }, [project.id]);

  useEffect(() => {
    const drafts = {};
    (workflow?.steps || []).forEach((step) => {
      drafts[step.id] = step.prompt || "";
    });
    setPromptDrafts(drafts);
  }, [workflow]);

  useEffect(() => {
    if (!workflow) return;
    setForm((current) => ({
      ...current,
      product_name: current.product_name || workflow.product_name || "",
      material: current.material || workflow.material || "",
      style_key: current.style_key || workflow.style_key || "natural_fashion",
      image_model: current.image_model || workflow.image_model || "gpt-image-2-client",
      size: current.size || workflow.size || "1024x1024",
      quality: current.quality || workflow.quality || "high",
      product_asset_id: current.product_asset_id || workflow.product_asset_id || "",
      model_asset_id: current.model_asset_id || workflow.model_asset_id || "",
      scene_asset_id: current.scene_asset_id || workflow.scene_asset_id || "",
      fit_front_asset_id: current.fit_front_asset_id || workflow.fit_front_asset_id || "",
      fit_side_asset_id: current.fit_side_asset_id || workflow.fit_side_asset_id || "",
      fit_back_asset_id: current.fit_back_asset_id || workflow.fit_back_asset_id || "",
      accessory_asset_id: current.accessory_asset_id || workflow.accessory_asset_id || "",
    }));
  }, [workflow]);

  useEffect(() => {
    if (!workflow || workflow.workflow_status !== "running") return;
    const interval = setInterval(async () => {
      try {
        const updated = await request(`/api/projects/${project.id}/workflow`);
        setWorkflow(updated);
        if (updated.workflow_status !== "running") {
          clearInterval(interval);
          await refresh();
        }
      } catch (err) {
        console.warn("Auto-refresh failed", err);
      }
    }, 10000);
    return () => clearInterval(interval);
  }, [workflow?.project_id, workflow?.workflow_status]);

  const ready =
    form.product_name.trim() &&
    form.material.trim() &&
    form.style_key &&
    form.image_model &&
    form.size &&
    form.quality &&
    form.product_asset_id &&
    form.model_asset_id &&
    form.scene_asset_id &&
    form.fit_front_asset_id &&
    form.fit_side_asset_id &&
    form.fit_back_asset_id &&
    form.accessory_asset_id;

  const initWorkflow = async () => {
    return request(`/api/projects/${project.id}/workflow`, {
      method: "POST",
      body: JSON.stringify({ ...form, project_id: project.id }),
    });
  };

  const uploadOne = async (ref, assetType, slot, notes) => {
    const file = ref.current?.files?.[0];
    if (!file) return "";
    const data = new FormData();
    data.append("project_id", project.id);
    data.append("asset_type", assetType);
    data.append("slot", slot);
    data.append("notes", notes);
    data.append("files", file);
    const uploaded = await request("/api/assets", { method: "POST", body: data });
    ref.current.value = "";
    return uploaded[0]?.id || "";
  };

  const uploadRequiredAssets = async () => {
    setBusy(true);
    try {
      const [productId, fitFrontId, fitSideId, fitBackId] = await Promise.all([
        uploadOne(productFileRef, "product", "product_image", "固定九图流程：产品图"),
        uploadOne(fitFrontFileRef, "competitor", "fit_reference", "固定九图流程：上身效果正面参考图"),
        uploadOne(fitSideFileRef, "competitor", "fit_reference", "固定九图流程：上身效果侧面参考图"),
        uploadOne(fitBackFileRef, "competitor", "fit_reference", "固定九图流程：上身效果背面参考图"),
      ]);
      setForm((current) => ({
        ...current,
        product_asset_id: productId || current.product_asset_id,
        fit_front_asset_id: fitFrontId || current.fit_front_asset_id,
        fit_side_asset_id: fitSideId || current.fit_side_asset_id,
        fit_back_asset_id: fitBackId || current.fit_back_asset_id,
      }));
      if (productId || fitFrontId || fitSideId || fitBackId) {
        setWorkflow(null);
      }
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const savePrompt = async (stepId, prompt) => {
    const updated = await request(`/api/projects/workflow/steps/${stepId}`, {
      method: "PATCH",
      body: JSON.stringify({ prompt }),
    });
    setWorkflow((current) => current ? { ...current, steps: (current.steps || []).map((step) => step.id === stepId ? { ...step, ...updated } : step) } : current);
  };

  const saveAllPrompts = async () => {
    const steps = workflow?.steps || [];
    await Promise.all(steps.map((step) => savePrompt(step.id, promptDrafts[step.id] ?? step.prompt ?? "")));
  };

  const preview = async () => {
    if (!ready) return;
    setBusy(true);
    try {
      const wf = await initWorkflow();
      const detailed = await request(`/api/projects/${project.id}/workflow/preview`, { method: "POST" });
      setWorkflow(detailed);
      await refresh();
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (!ready && !workflow) return;
    setBusy(true);
    try {
      let wf = workflow;
      if (!wf) {
        wf = await initWorkflow();
        setWorkflow(wf);
      }
      if (wf) await saveAllPrompts();
      await request(`/api/projects/${project.id}/workflow/generate`, {
        method: "POST",
        body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
      });
      setWorkflow(await request(`/api/projects/${project.id}/workflow`));
      await refresh();
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const downloadRun = async () => {
    if (!workflow || !docxRunReadyToDownload(workflow)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/projects/${project.id}/workflow/download`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match?.[1] || `${project.sku || "固定九图流程"}_images.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
      onDownload?.();
    } finally {
      setBusy(false);
    }
  };

  const regenerateStep = async (stepId) => {
    if (!workflow) return;
    setBusy(true);
    try {
      const prompt = promptDrafts[stepId] ?? workflow.steps?.find((step) => step.id === stepId)?.prompt ?? "";
      await savePrompt(stepId, prompt);
      setWorkflow((current) => current ? {
        ...current,
        steps: (current.steps || []).map((step) => step.id === stepId ? { ...step, status: "running", error: "", url: "" } : step),
      } : current);
      const generated = await request(`/api/projects/workflow/steps/${stepId}/generate`, {
        method: "POST",
        body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
      });
      setWorkflow(generated);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const refreshWorkflow = async () => {
    try {
      const updated = await request(`/api/projects/${project.id}/workflow`);
      setWorkflow(updated);
    } catch {
      setWorkflow(null);
    }
  };

  const updateStepPoseRef = async (step, newAssetId) => {
    setBusy(true);
    try {
      const updated = await request(`/api/projects/workflow/steps/${step.id}/pose-ref`, {
        method: "PATCH",
        body: JSON.stringify({ pose_asset_id: newAssetId }),
      });
      setWorkflow(updated);
      await refresh();
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const isPoseAsset = (assetId) => {
    const asset = assets.find((a) => a.id === assetId);
    return asset?.slot === "pose_reference";
  };

  const getStepPoseAssetId = (step) => {
    const refs = step.input_refs || [];
    for (const ref of refs) {
      if (ref.type === "asset" && isPoseAsset(ref.id)) return ref.id;
    }
    return "";
  };

  const getStepPoseAssets = (step) => {
    if (!step.pose_slot) return [];
    const refs = step.input_refs || [];
    return refs
      .filter((ref) => ref.type === "asset" && isPoseAsset(ref.id))
      .map((ref) => assets.find((a) => a.id === ref.id))
      .filter(Boolean);
  };

  const markKnowledgeCandidate = async (step) => {
    if (!step?.id || !step.url) return;
    setBusy(true);
    try {
      await request(`/api/projects/workflow/steps/${step.id}/knowledge-candidate`, {
        method: "POST",
        body: JSON.stringify({
          rating: 5,
          review_notes: "九图流程人工标记候选",
          suggested_category: project.category || "",
          suggested_scene: "",
          suggested_image_type: step.title || "",
          suggested_metadata: {
            sku: project.sku,
            project_name: project.name,
            docx_stage_id: step.stage_id,
            image_no: step.image_no,
          },
        }),
      });
      alert("已保存为知识库候选");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel docx-workflow-panel">
      <div className="section-title">
        <FileImage size={18} />
        <h2>固定九图流程</h2>
      </div>
      <div className="docx-upload-grid">
        <label className="stacked-field">
          <span>产品图</span>
          <input ref={productFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>上身效果正面参考图</span>
          <input ref={fitFrontFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>上身效果侧面参考图</span>
          <input ref={fitSideFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>上身效果背面参考图</span>
          <input ref={fitBackFileRef} type="file" accept="image/*" />
        </label>
      </div>
      <button className="primary" disabled={busy} onClick={uploadRequiredAssets}>
        <Upload size={16} />
        上传并填入参考图
      </button>
      <div className="docx-config-grid">
        <label className="stacked-field">
          <span>产品名称</span>
          <input placeholder="例如：白色双层可调节吊带背心" value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} />
        </label>
        <label className="stacked-field">
          <span>材质</span>
          <input placeholder="例如：SmoothSpandexfabric，Plainweave" value={form.material} onChange={(e) => setForm({ ...form, material: e.target.value })} />
        </label>
        <label className="stacked-field">
          <span>输出规格风格</span>
          <select value={form.style_key} onChange={(e) => setForm({ ...form, style_key: e.target.value })}>
            {styles.map((style) => (
              <option key={style.key} value={style.key}>
                {style.label}
              </option>
            ))}
          </select>
        </label>
        <label className="stacked-field">
          <span>生图模型</span>
          <select value={form.image_model} onChange={(e) => setForm({ ...form, image_model: e.target.value })}>
            {imageModels.length ? imageModels.map((item) => (
              <option key={item.model} value={item.model}>
                {item.model} ({item.key_count} keys · {item.api_type})
              </option>
            )) : (
              <option value="gpt-image-2-client">gpt-image-2-client</option>
            )}
          </select>
          <small>{imageModels.find((item) => item.model === form.image_model)?.key_count || 0} 个 key，将按模型独立轮换。</small>
        </label>
        <label className="stacked-field">
          <span>图片尺寸</span>
          <select value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}>
            {["2048x2048", "2048x1152", "1152x2048", "1024x1024", "1024x1536", "1536x1024", "3072x1024"].map((size) => (
              <option key={size} value={size}>{size}</option>
            ))}
          </select>
        </label>
        <label className="stacked-field">
          <span>图片质量</span>
          <select value={form.quality} onChange={(e) => setForm({ ...form, quality: e.target.value })}>
            {["low", "medium", "high"].map((quality) => (
              <option key={quality} value={quality}>{quality}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="docx-asset-grid">
        <DocxAssetSelect label="产品图" assets={assets} slotHint="product_image" value={form.product_asset_id} onChange={(value) => setForm({ ...form, product_asset_id: value })} />
        <DocxAssetSelect label="模特参考图" assets={assets} slotHint="model_reference" value={form.model_asset_id} onChange={(value) => setForm({ ...form, model_asset_id: value })} />
        <DocxAssetSelect label="场景风格参考图" assets={assets} slotHint="scene_reference" value={form.scene_asset_id} onChange={(value) => setForm({ ...form, scene_asset_id: value })} />
        <DocxAssetSelect label="上身效果正面参考图" assets={assets} slotHint="fit_reference" value={form.fit_front_asset_id} onChange={(value) => setForm({ ...form, fit_front_asset_id: value })} />
        <DocxAssetSelect label="上身效果侧面参考图" assets={assets} slotHint="fit_reference" value={form.fit_side_asset_id} onChange={(value) => setForm({ ...form, fit_side_asset_id: value })} />
        <DocxAssetSelect label="上身效果背面参考图" assets={assets} slotHint="fit_reference" value={form.fit_back_asset_id} onChange={(value) => setForm({ ...form, fit_back_asset_id: value })} />
        <DocxAssetSelect label="配饰参考图" assets={assets} slotHint="accessory_reference" value={form.accessory_asset_id} onChange={(value) => setForm({ ...form, accessory_asset_id: value })} />
      </div>
      <div className="docx-actions">
        <button className="primary" disabled={!ready || busy} onClick={preview}>
          <FileImage size={16} />
          预览 9 张提示词
        </button>
        <button className="primary" disabled={(!ready && !workflow) || busy} onClick={generate}>
          <Sparkles size={16} />
          一键生成 9 张图
        </button>
        <button disabled={!docxRunReadyToDownload(workflow) || busy} onClick={downloadRun}>
          一键下载 9 张图
        </button>
      </div>
      {(() => {
        const refFields = [
          { id: form.product_asset_id, label: "产品图" },
          { id: form.model_asset_id, label: "模特参考" },
          { id: form.scene_asset_id, label: "场景参考" },
          { id: form.fit_front_asset_id, label: "上身正面" },
          { id: form.fit_side_asset_id, label: "上身侧面" },
          { id: form.fit_back_asset_id, label: "上身背面" },
          { id: form.accessory_asset_id, label: "配饰参考" },
        ].filter((f) => f.id);
        const poseAssets = assets.filter((a) => a.slot === "pose_reference" && a.url);
        if (!refFields.length && !poseAssets.length) return null;
        return (
          <div className="docx-ref-overview">
            <strong>参考图总览：</strong>
            <div className="docx-ref-overview-grid">
              {refFields.map((f) => {
                const asset = assets.find((a) => a.id === f.id);
                if (!asset?.url) return null;
                return (
                  <div key={f.id} className="docx-ref-overview-item" title={`${f.label} · ${asset.original_name}`}>
                    <img src={`${API}${asset.url}`} alt={asset.original_name} className="clickable-img" onClick={() => setPreviewImage({ src: `${API}${asset.url}`, alt: asset.original_name })} />
                    <span>{asset.original_name}</span>
                  </div>
                );
              })}
              {poseAssets.map((a) => (
                <div key={a.id} className="docx-ref-overview-item" title={`姿势参考 · ${a.original_name}`}>
                  <img src={`${API}${a.url}`} alt={a.original_name} className="clickable-img" onClick={() => setPreviewImage({ src: `${API}${a.url}`, alt: a.original_name })} />
                  <span>{a.original_name}</span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}
      {workflow ? (
        <div className="docx-preview">
          <div className="prompt-head">
            <strong>{workflow.product_name || project.name} / {workflow.material || ""}</strong>
            <span>{workflow.workflow_status || workflow.status}</span>
          </div>
          <div className="workflow-step-grid">
            {(workflow.steps || []).map((step) => (
              <article key={step.id} className={`workflow-step ${step.status}`}>
                <div className="workflow-step-head">
                  <span>#{step.image_no}</span>
                  <strong>{step.title}</strong>
                  <em>{step.status}</em>
                </div>
                {step.url ? <img src={`${API}${step.url}`} alt={step.title} className="clickable-img" onClick={() => setPreviewImage({ src: `${API}${step.url}`, alt: step.title })} /> : <div className="step-placeholder">{step.error || "等待生成"}</div>}
                <textarea
                  value={promptDrafts[step.id] ?? step.prompt ?? ""}
                  onChange={(event) => setPromptDrafts({ ...promptDrafts, [step.id]: event.target.value })}
                />
                {(() => {
                  const baseItems = (step.reference_items || []).filter((item) => item.type !== "rag" && item.slot !== "pose_reference");
                  const poseAssets = getStepPoseAssets(step);
                  const hasAny = baseItems.length || poseAssets.length || step.pose_slot;
                  if (!hasAny) return null;
                  return (
                    <div className="step-base-refs">
                      <strong>基础参考：</strong>
                      {baseItems.map((item) => (
                        <div key={item.id} className="step-base-ref-item">
                          {item.url ? <img src={`${API}${item.url}`} alt={item.label} className="step-base-ref-thumb clickable-img" onClick={() => setPreviewImage({ src: `${API}${item.url}`, alt: item.label })} /> : null}
                          <div className="step-base-ref-text">
                            <span>图{item.order} {item.label}</span>
                            <small>{item.type === "step" ? `前置步骤 · ${item.status || "待生成"}` : item.slot || item.asset_type || ""}</small>
                          </div>
                        </div>
                      ))}
                      {poseAssets.map((a) => (
                        <div key={a.id} className="step-base-ref-item">
                          {a.url ? <img src={`${API}${a.url}`} alt={a.original_name} className="step-base-ref-thumb clickable-img" onClick={() => setPreviewImage({ src: `${API}${a.url}`, alt: a.original_name })} /> : null}
                          <div className="step-base-ref-text">
                            <span>姿势参考 · {a.original_name}</span>
                            <small>pose_reference</small>
                          </div>
                        </div>
                      ))}
                      {step.pose_slot ? (
                        <div className="step-pose-select">
                          <span>切换姿势：</span>
                          <select
                            value={getStepPoseAssetId(step)}
                            onChange={(e) => updateStepPoseRef(step, e.target.value)}
                          >
                            <option value="">无</option>
                            {assets.filter((a) => a.slot === "pose_reference" && a.url).map((a) => (
                              <option key={a.id} value={a.id}>{a.original_name}</option>
                            ))}
                          </select>
                        </div>
                      ) : null}
                    </div>
                  );
                })()}
                <div className="docx-actions">
                  <button onClick={() => savePrompt(step.id, promptDrafts[step.id] ?? step.prompt ?? "")}>保存提示词</button>
                  <button onClick={() => regenerateStep(step.id)} disabled={busy}>重新生成本张</button>
                  <button onClick={() => markKnowledgeCandidate(step)} disabled={busy || !step.url}>
                    <Star size={14} />
                    标记知识库候选
                  </button>
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
      <ImagePreviewModal
        src={previewImage?.src}
        alt={previewImage?.alt}
        onClose={() => setPreviewImage(null)}
      />
    </section>
  );
}

function UserSelectScreen({ users, onSelect, onCreate }) {
  const [name, setName] = useState("");
  return (
    <div className="centered-screen">
      <div className="centered-card">
        <h1>选择用户</h1>
        <p>请选择一个用户，或创建新用户来管理项目。</p>
        <div className="user-create-row">
          <input
            placeholder="输入新用户名"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && name.trim()) { onCreate(name.trim()); setName(""); } }}
          />
          <button
            className="primary"
            disabled={!name.trim()}
            onClick={() => { onCreate(name.trim()); setName(""); }}
          >
            <Plus size={16} />
            创建用户
          </button>
        </div>
        <div className="user-list">
          {users.map((user) => (
            <button
              key={user.id}
              className="user-card"
              onClick={() => onSelect(user)}
            >
              <strong>{user.name}</strong>
              <small>{user.created_at}</small>
            </button>
          ))}
          {users.length === 0 && (
            <p className="muted">还没有用户，请先创建一个。</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectSelectScreen({ user, projects, onSelect, onCreate, onDelete, onBack }) {
  const [form, setForm] = useState({ sku: "", category: "", name: "", notes: "" });
  const [search, setSearch] = useState("");
  const filtered = search.trim()
    ? projects.filter((p) => (p.sku || "").toLowerCase().includes(search.trim().toLowerCase()))
    : projects;
  const handleCreate = () => {
    if (!form.sku.trim()) return;
    onCreate(form);
    setForm({ sku: "", category: "", name: "", notes: "" });
  };
  return (
    <div className="centered-screen">
      <div className="centered-card wide-card">
        <div className="centered-card-header">
          <button className="ghost" onClick={onBack}>← 返回</button>
          <h1>{user.name} 的项目</h1>
        </div>
        <div className="project-create-form">
          <div className="project-create-row">
            <input placeholder="SKU（必填）" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
            <input placeholder="品类" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </div>
          <input placeholder="项目名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <textarea placeholder="备注" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button className="primary" disabled={!form.sku.trim()} onClick={handleCreate}>
            <Plus size={16} />
            创建项目
          </button>
        </div>
        <div className="project-overview-search">
          <Search size={14} />
          <input placeholder="搜索 SKU…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="project-select-list">
          {filtered.map((project) => (
            <div key={project.id} className="project-select-card-wrap">
              <button
                className="project-select-card"
                onClick={() => onSelect(project)}
              >
                <strong>{project.sku}</strong>
                <span>{project.name}</span>
                <small>{project.category || "未分类"}</small>
                <WorkflowStatusBadge project={project} />
                <StepProgress project={project} />
              </button>
              <button className="icon-btn danger project-delete-btn" title="删除项目" onClick={() => onDelete(project.id)}>
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="muted">{search.trim() ? "没有匹配的项目。" : "该用户还没有项目，请先创建一个。"}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [phase, setPhase] = useState("user");
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [error, setError] = useState("");
  const docxFormSetter = useRef(null);

  const loadUsers = async () => {
    try {
      setError("");
      const data = await request("/api/users");
      setUsers(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const loadProjects = async (userId) => {
    if (!userId) return;
    try {
      setError("");
      const projectList = await request(`/api/projects?user_id=${userId}`);
      setProjects(projectList);
    } catch (err) {
      setError(err.message);
    }
  };

  const loadProjectDetail = async () => {
    if (!selectedProject) return;
    try {
      setProjectDetail(await request(`/api/projects/${selectedProject.id}`));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    if (selectedUser) {
      loadProjects(selectedUser.id);
    }
  }, [selectedUser]);

  useEffect(() => {
    loadProjectDetail();
  }, [selectedProject]);

  const createProject = async (form) => {
    const project = await request("/api/projects", { method: "POST", body: JSON.stringify({ ...form, user_id: selectedUser.id }) });
    setSelectedProject(project);
    setPhase("workspace");
    await loadProjects(selectedUser.id);
  };
  const deleteProject = async (id) => {
    if (!confirm("确认删除该项目？所有相关素材和记录都会被删除。")) return;
    await request(`/api/projects/${id}`, { method: "DELETE" });
    if (selectedProject?.id === id) setSelectedProject(null);
    await loadProjects(selectedUser.id);
  };

  const assets = projectDetail?.assets || [];

  if (phase === "user") {
    return (
      <div className="app-shell">
        <header>
          <div>
            <h1>固定九图自动化生图流程</h1>
            <p>请先选择或创建一个用户。</p>
          </div>
        </header>
        {error ? <div className="error-banner">{error}</div> : null}
        <UserSelectScreen
          users={users}
          onSelect={(user) => { setSelectedUser(user); setPhase("project"); }}
          onCreate={async (name) => {
            const user = await request("/api/users", { method: "POST", body: JSON.stringify({ name }) });
            setUsers((prev) => [user, ...prev]);
            setSelectedUser(user);
            setPhase("project");
          }}
        />
      </div>
    );
  }

  if (phase === "project") {
    return (
      <div className="app-shell">
        <header>
          <div>
            <h1>固定九图自动化生图流程</h1>
            <p>当前用户：{selectedUser?.name}。选择或创建一个项目。</p>
          </div>
        </header>
        {error ? <div className="error-banner">{error}</div> : null}
        <ProjectSelectScreen
          user={selectedUser}
          projects={projects}
          onSelect={(project) => { setSelectedProject(project); setPhase("workspace"); }}
          onCreate={createProject}
          onDelete={deleteProject}
          onBack={() => { setSelectedUser(null); setSelectedProject(null); setProjectDetail(null); setPhase("user"); }}
        />
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header>
        <div>
          <h1>DOCX 固定九图自动化生图流程</h1>
          <p>{selectedUser?.name} / {selectedProject?.name || selectedProject?.sku}</p>
        </div>
        <div className="header-right">
          <div className="status-pill">{selectedProject ? selectedProject.sku : "未选择项目"}</div>
          <button className="ghost" onClick={() => { setPhase("project"); loadProjects(selectedUser.id); }}>切换项目</button>
          <button className="ghost" onClick={() => { setSelectedUser(null); setSelectedProject(null); setProjectDetail(null); setPhase("user"); }}>切换用户</button>
        </div>
      </header>
      {error ? <div className="error-banner">{error}</div> : null}
      <main className="no-sidebar">
        {selectedProject && projectDetail ? (
          <div className="workspace">
            <RagKnowledgeWorkbench
              project={selectedProject}
              refreshProject={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)}
              onAssetCreated={(asset, slot) => {
                if (!docxFormSetter.current) return;
                const fieldMap = {
                  model_reference: "model_asset_id",
                  scene_reference: "scene_asset_id",
                  pose_reference: "pose_reference",
                  accessory_reference: "accessory_asset_id",
                };
                const field = fieldMap[slot];
                if (field && field !== "pose_reference") {
                  docxFormSetter.current((prev) => ({ ...prev, [field]: asset.id }));
                }
              }}
            />
            <DocxWorkflowPanel
              project={selectedProject}
              assets={assets}
              refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)}
              onDownload={() => loadProjects(selectedUser.id)}
              formSetterRef={docxFormSetter}
            />
          </div>
        ) : (
          <section className="empty-state">请从左侧选择一个项目。</section>
        )}
      </main>
    </div>
  );
}
