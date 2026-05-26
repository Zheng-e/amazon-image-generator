import {
  Check,
  Database,
  FileImage,
  FlaskConical,
  ImagePlus,
  Plus,
  Save,
  Search,
  Sparkles,
  Star,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

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

function docxRunReadyToDownload(run) {
  const steps = run?.steps || [];
  return steps.length === 9 && steps.every((step) => step.status === "success" && step.url);
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

function ProjectPanel({ projects, selectedProject, setSelectedProject, onCreate, onDelete }) {
  const [form, setForm] = useState({ sku: "", category: "", name: "", notes: "" });
  return (
    <section className="panel compact">
      <div className="section-title">
        <FlaskConical size={18} />
        <h2>项目</h2>
      </div>
      <div className="form-grid">
        <input placeholder="SKU" value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
        <input placeholder="品类" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
        <input placeholder="项目名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <textarea placeholder="备注" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
      </div>
      <button className="primary wide" onClick={() => onCreate(form)}>
        <Plus size={16} />
        创建项目
      </button>
      <div className="project-list">
        {projects.map((project) => (
          <div key={project.id} className={selectedProject?.id === project.id ? "project-row active" : "project-row"}>
            <button className="project" onClick={() => setSelectedProject(project)}>
              <strong>{project.sku}</strong>
              <span>{project.name}</span>
            </button>
            <button className="icon-btn danger" title="删除项目" onClick={(e) => { e.stopPropagation(); onDelete(project.id); }}>
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function AssetPanel({ project, assets, refresh }) {
  const [assetType, setAssetType] = useState("product");
  const [files, setFiles] = useState([]);
  const [meta, setMeta] = useState({ source_url: "", asin: "", keyword: "", slot: "", notes: "" });
  const grouped = useMemo(() => {
    return assets.reduce((acc, asset) => {
      acc[asset.asset_type] = [...(acc[asset.asset_type] || []), asset];
      return acc;
    }, {});
  }, [assets]);

  const deleteAsset = async (id) => {
    if (!confirm("确认删除这张图片？")) return;
    await request(`/api/assets/${id}`, { method: "DELETE" });
    await refresh();
  };

  const upload = async () => {
    if (!project || !files.length) return;
    const form = new FormData();
    form.append("project_id", project.id);
    form.append("asset_type", assetType);
    Object.entries(meta).forEach(([key, value]) => form.append(key, value));
    files.forEach((file) => form.append("files", file));
    await request("/api/assets", { method: "POST", body: form });
    setFiles([]);
    await refresh();
  };

  return (
    <section className="panel">
      <div className="section-title">
        <ImagePlus size={18} />
        <h2>素材上传</h2>
      </div>
      <div className="upload-bar">
        <select value={assetType} onChange={(e) => setAssetType(e.target.value)}>
          <option value="product">商品参考图</option>
          <option value="model">模特参考图</option>
          <option value="competitor">竞品图</option>
        </select>
        <input type="file" multiple accept="image/*" onChange={(e) => setFiles([...e.target.files])} />
        <button className="primary" onClick={upload}>
          <Upload size={16} />
          上传
        </button>
      </div>
      <div className="meta-grid">
        <select value={meta.slot} onChange={(e) => setMeta({ ...meta, slot: e.target.value })}>
          <option value="">素材用途（可选）</option>
          <option value="product_image">产品图</option>
          <option value="model_reference">模特面部及身材参考图</option>
          <option value="fit_reference">衣服上身效果参考图</option>
          <option value="scene_style_reference">场景风格参考图</option>
        </select>
        <input placeholder="关键词/标签" value={meta.keyword} onChange={(e) => setMeta({ ...meta, keyword: e.target.value })} />
        <input placeholder="来源 URL/ASIN" value={meta.source_url} onChange={(e) => setMeta({ ...meta, source_url: e.target.value })} />
        <input placeholder="备注" value={meta.notes} onChange={(e) => setMeta({ ...meta, notes: e.target.value })} />
      </div>
      <div className="asset-columns">
        {["product", "model", "competitor"].map((type) => (
          <div key={type}>
            <h3>{type === "product" ? "商品图" : type === "model" ? "模特图" : "竞品图"}</h3>
            <div className="asset-grid">
              {(grouped[type] || []).map((asset) => (
                <figure key={asset.id}>
                  {asset.url ? (
                    <img src={`${API}${asset.url}`} alt={asset.original_name} />
                  ) : (
                    <div className="asset-missing">文件缺失<br />请删除后重新上传</div>
                  )}
                  <figcaption title={asset.original_name}>
                    {asset.original_name}
                    {asset.slot ? <small>{asset.slot}</small> : null}
                  </figcaption>
                  <button className="icon-btn danger figure-del" title="删除" onClick={() => deleteAsset(asset.id)}>
                    <Trash2 size={12} />
                  </button>
                </figure>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RagKnowledgeWorkbench({ project, refreshProject }) {
  const [health, setHealth] = useState(null);
  const [query, setQuery] = useState(defaultRagQuery(project));
  const [topK, setTopK] = useState(8);
  const [filterText, setFilterText] = useState("");
  const [results, setResults] = useState([]);
  const [references, setReferences] = useState([]);
  const [selectedTags, setSelectedTags] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [previewImage, setPreviewImage] = useState(null);

  const loadReferences = async () => {
    if (!project?.id) return;
    const data = await request(`/api/projects/${project.id}/rag-references`);
    setReferences(data);
  };

  useEffect(() => {
    setQuery(defaultRagQuery(project));
    setResults([]);
    setError("");
    request("/api/rag/health").then(setHealth).catch((err) => setHealth({ status: "unavailable", detail: err.message }));
    loadReferences().catch((err) => setError(err.message));
  }, [project?.id]);

  const parseFilters = () => {
    const text = filterText.trim();
    if (!text) return {};
    try {
      const parsed = JSON.parse(text);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      throw new Error("过滤条件必须是 JSON 对象，例如 {\"compliance\":\"approved\"}");
    }
  };

  const search = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      const data = await request("/api/rag/search", {
        method: "POST",
        body: JSON.stringify({ query, top_k: topK, filters: parseFilters() }),
      });
      setResults(data.results || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const addReference = async (item) => {
    const usage_tags = selectedTags[item.image_id] || ["scene_reference"];
    setBusy(true);
    setError("");
    try {
      await request(`/api/projects/${project.id}/rag-references`, {
        method: "POST",
        body: JSON.stringify({
          rag_image_id: item.image_id,
          filename: item.filename || "",
          category: item.category || "",
          scene: item.scene || "",
          image_type: item.image_type || "",
          caption: item.caption || "",
          score: item.score ?? null,
          usage_tags,
          metadata: item.metadata || {},
          notes: "从知识库工作台加入",
        }),
      });
      await loadReferences();
      await refreshProject();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const updateReferenceTags = async (reference, tag, checked) => {
    const current = new Set(reference.usage_tags || []);
    if (checked) current.add(tag);
    else current.delete(tag);
    const usage_tags = [...current];
    const updated = await request(`/api/projects/${project.id}/rag-references/${reference.id}`, {
      method: "PATCH",
      body: JSON.stringify({ usage_tags }),
    });
    setReferences((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  };

  const updateModelDescription = async (reference, description) => {
    const updated = await request(`/api/projects/${project.id}/rag-references/${reference.id}`, {
      method: "PATCH",
      body: JSON.stringify({ model_description: description }),
    });
    setReferences((items) => items.map((item) => (item.id === updated.id ? updated : item)));
  };

  const removeReference = async (referenceId) => {
    if (!confirm("确认从本项目参考池移除这张知识库图片？")) return;
    await request(`/api/projects/${project.id}/rag-references/${referenceId}`, { method: "DELETE" });
    await loadReferences();
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
      <div className="rag-search-grid">
        <label className="stacked-field">
          <span>检索词</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label className="stacked-field">
          <span>返回数量</span>
          <input type="number" min="1" max="20" value={topK} onChange={(event) => setTopK(Number(event.target.value) || 8)} />
        </label>
        <label className="stacked-field">
          <span>过滤 JSON</span>
          <input placeholder='{"compliance":"approved"}' value={filterText} onChange={(event) => setFilterText(event.target.value)} />
        </label>
        <button className="primary" disabled={busy || !query.trim()} onClick={search}>
          <Search size={16} />
          搜索知识库
        </button>
      </div>
      {error ? <div className="error-banner">{error}</div> : null}
      <div className="rag-results-grid">
        {results.map((item) => (
          <article key={item.image_id} className="rag-card">
            <img src={`${API}/api/rag/images/${item.image_id}`} alt={item.filename || item.image_id} className="clickable-img" onClick={() => setPreviewImage({ src: `${API}/api/rag/images/${item.image_id}`, alt: item.filename || item.image_id })} />
            <div className="rag-card-body">
              <strong>{item.filename || item.image_id}</strong>
              <span>{item.category || "未分类"} · {item.scene || "未知场景"}</span>
              <small>{item.image_type || item.caption || ""}</small>
              <em>相似度：{typeof item.score === "number" ? item.score.toFixed(4) : "-"}</em>
              <select
                value={(selectedTags[item.image_id] || ["scene_reference"])[0]}
                onChange={(event) => setSelectedTags({ ...selectedTags, [item.image_id]: [event.target.value] })}
              >
                {RAG_USAGE_TAGS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button disabled={busy} onClick={() => addReference(item)}>
                <Check size={14} />
                加入本项目
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="rag-reference-pool">
        <div className="prompt-head">
          <strong>项目参考池</strong>
          <span>{references.length} 张</span>
        </div>
        {references.length ? references.map((reference) => (
          <article key={reference.id} className="rag-reference-row">
            <img src={`${API}${reference.image_url}`} alt={reference.filename || reference.rag_image_id} className="clickable-img" onClick={() => setPreviewImage({ src: `${API}${reference.image_url}`, alt: reference.filename || reference.rag_image_id })} />
            <div>
              <strong>{reference.filename || reference.rag_image_id}</strong>
              <small>{reference.scene || reference.caption || ""}</small>
              <div className="tag-grid">
                {RAG_USAGE_TAGS.map(([value, label]) => (
                  <label key={value}>
                    <input
                      type="checkbox"
                      checked={(reference.usage_tags || []).includes(value)}
                      onChange={(event) => updateReferenceTags(reference, value, event.target.checked)}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <label className="stacked-field rag-model-desc">
                <span>这张图是什么（给模型看的说明）</span>
                <textarea
                  value={reference.model_description || ""}
                  onChange={(event) => setReferences((items) => items.map((item) => item.id === reference.id ? { ...item, model_description: event.target.value } : item))}
                  onBlur={(event) => updateModelDescription(reference, event.target.value)}
                  rows={2}
                />
              </label>
              <div className="rag-applied-steps">
                <strong>预计用于：</strong>
                {(reference.applied_steps || []).length ? (
                  <span>
                    {reference.applied_steps.map((s) => `第${s.image_no}张 ${s.title}`).join("、")}
                  </span>
                ) : (
                  <span className="muted">未分配，请选择用途标签</span>
                )}
              </div>
            </div>
            <button className="icon-btn danger" title="移除" onClick={() => removeReference(reference.id)}>
              <X size={14} />
            </button>
          </article>
        )) : <p className="muted">还没有加入本项目的知识库参考图。</p>}
      </div>
      <ImagePreviewModal
        src={previewImage?.src}
        alt={previewImage?.alt}
        onClose={() => setPreviewImage(null)}
      />
    </section>
  );
}

const DOCX_SLOT_TYPES = {
  product_image: ["product"],
  model_reference: ["model"],
  fit_reference: ["competitor"],
  scene_style_reference: ["competitor"],
};

const DOCX_SLOT_LABELS = {
  product_image: "产品图",
  model_reference: "模特参考",
  fit_reference: "上身效果参考",
  scene_style_reference: "场景风格参考",
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

function DocxWorkflowPanel({ project, assets, runs, refresh }) {
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
    fit_asset_id: "",
    scene_asset_id: "",
  });
  const [activeRun, setActiveRun] = useState(null);
  const [promptDrafts, setPromptDrafts] = useState({});
  const [busy, setBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const productFileRef = useRef(null);
  const modelFileRef = useRef(null);
  const fitFileRef = useRef(null);
  const sceneFileRef = useRef(null);

  useEffect(() => {
    request("/api/docx-workflow/styles").then(setStyles).catch(() => setStyles([]));
    request("/api/models/image").then((models) => {
      setImageModels(models);
      setForm((current) => current.image_model ? current : { ...current, image_model: models[0]?.model || "gpt-image-2-client" });
    }).catch(() => setImageModels([]));
  }, []);

  useEffect(() => {
    setActiveRun(null);
  }, [project.id]);

  useEffect(() => {
    setActiveRun(null);
  }, [form.product_name, form.material, form.style_key, form.image_model, form.size, form.quality, form.product_asset_id, form.model_asset_id, form.fit_asset_id, form.scene_asset_id]);

  useEffect(() => {
    const drafts = {};
    (activeRun?.steps || []).forEach((step) => {
      drafts[step.id] = step.prompt || "";
    });
    setPromptDrafts(drafts);
  }, [activeRun]);

  const ready =
    form.product_name.trim() &&
    form.material.trim() &&
    form.style_key &&
    form.image_model &&
    form.size &&
    form.quality &&
    form.product_asset_id &&
    form.model_asset_id &&
    form.fit_asset_id &&
    form.scene_asset_id;

  const createRun = async () => {
    return request("/api/docx-workflow/runs", {
      method: "POST",
      body: JSON.stringify({ project_id: project.id, ...form }),
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
      const [productId, modelId, fitId, sceneId] = await Promise.all([
        uploadOne(productFileRef, "product", "product_image", "DOCX流程：产品图"),
        uploadOne(modelFileRef, "model", "model_reference", "DOCX流程：模特面部及身材参考图"),
        uploadOne(fitFileRef, "competitor", "fit_reference", "DOCX流程：衣服上身效果参考图"),
        uploadOne(sceneFileRef, "competitor", "scene_style_reference", "DOCX流程：场景风格参考图"),
      ]);
      setForm((current) => ({
        ...current,
        product_asset_id: productId || current.product_asset_id,
        model_asset_id: modelId || current.model_asset_id,
        fit_asset_id: fitId || current.fit_asset_id,
        scene_asset_id: sceneId || current.scene_asset_id,
      }));
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const savePrompt = async (stepId, prompt) => {
    const updated = await request(`/api/docx-workflow/steps/${stepId}`, {
      method: "PATCH",
      body: JSON.stringify({ prompt }),
    });
    setActiveRun((current) => current ? { ...current, steps: (current.steps || []).map((step) => step.id === stepId ? { ...step, ...updated } : step) } : current);
  };

  const saveAllPrompts = async () => {
    const steps = activeRun?.steps || [];
    await Promise.all(steps.map((step) => savePrompt(step.id, promptDrafts[step.id] ?? step.prompt ?? "")));
  };

  const preview = async () => {
    if (!ready) return;
    setBusy(true);
    try {
      const run = await createRun();
      const detailed = await request(`/api/docx-workflow/runs/${run.id}/preview`, { method: "POST" });
      setActiveRun(detailed);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (!ready && !activeRun) return;
    setBusy(true);
    try {
      const run = activeRun || (await createRun());
      if (activeRun) await saveAllPrompts();
      setActiveRun(await request(`/api/docx-workflow/runs/${run.id}`));
      const generatePromise = request(`/api/docx-workflow/runs/${run.id}/generate`, {
        method: "POST",
        body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
      });
      let finished = false;
      generatePromise.then(() => { finished = true; }, () => { finished = true; });
      while (!finished) {
        await sleep(2500);
        try {
          setActiveRun(await request(`/api/docx-workflow/runs/${run.id}`));
        } catch (err) {
          console.warn("DOCX run poll failed", err);
        }
      }
      const generated = await generatePromise;
      setActiveRun(generated);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const downloadRun = async () => {
    if (!activeRun?.id || !docxRunReadyToDownload(activeRun)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/docx-workflow/runs/${activeRun.id}/download`);
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const disposition = res.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match?.[1] || `${project.sku || "docx"}_${activeRun.id.slice(0, 8)}_images.zip`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  };

  const regenerateStep = async (stepId) => {
    if (!activeRun?.id) return;
    setBusy(true);
    try {
      const prompt = promptDrafts[stepId] ?? activeRun.steps?.find((step) => step.id === stepId)?.prompt ?? "";
      await savePrompt(stepId, prompt);
      setActiveRun((current) => current ? {
        ...current,
        steps: (current.steps || []).map((step) => step.id === stepId ? { ...step, status: "running", error: "", url: "" } : step),
      } : current);
      const generated = await request(`/api/docx-workflow/steps/${stepId}/generate`, {
        method: "POST",
        body: JSON.stringify({ image_model: form.image_model, size: form.size, quality: form.quality }),
      });
      setActiveRun(generated);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  const removeRagRefFromStep = async (step, ragRefId) => {
    const currentRefs = step.input_refs || [];
    const newRefs = currentRefs.filter((ref) => !(ref.type === "rag" && ref.id === ragRefId));
    setBusy(true);
    try {
      const updated = await request(`/api/docx-workflow/steps/${step.id}`, {
        method: "PATCH",
        body: JSON.stringify({ input_refs: newRefs }),
      });
      setActiveRun((current) => current ? { ...current, steps: (current.steps || []).map((s) => s.id === step.id ? { ...s, ...updated } : s) } : current);
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const markKnowledgeCandidate = async (step) => {
    if (!step?.id || !step.url) return;
    setBusy(true);
    try {
      await request(`/api/docx-workflow/steps/${step.id}/knowledge-candidate`, {
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

  const loadRun = async (runId) => {
    const run = await request(`/api/docx-workflow/runs/${runId}`);
    setActiveRun(run);
  };

  return (
    <section className="panel docx-workflow-panel">
      <div className="section-title">
        <FileImage size={18} />
        <h2>DOCX 固定九图流程</h2>
      </div>
      <div className="docx-upload-grid">
        <label className="stacked-field">
          <span>产品图</span>
          <input ref={productFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>模特面部及身材参考图</span>
          <input ref={modelFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>衣服上身效果参考图</span>
          <input ref={fitFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>场景风格参考图</span>
          <input ref={sceneFileRef} type="file" accept="image/*" />
        </label>
      </div>
      <button className="primary" disabled={busy} onClick={uploadRequiredAssets}>
        <Upload size={16} />
        上传并填入四张参考图
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
        <DocxAssetSelect label="模特面部及身材参考图" assets={assets} slotHint="model_reference" value={form.model_asset_id} onChange={(value) => setForm({ ...form, model_asset_id: value })} />
        <DocxAssetSelect label="衣服上身效果参考图" assets={assets} slotHint="fit_reference" value={form.fit_asset_id} onChange={(value) => setForm({ ...form, fit_asset_id: value })} />
        <DocxAssetSelect label="场景风格参考图" assets={assets} slotHint="scene_style_reference" value={form.scene_asset_id} onChange={(value) => setForm({ ...form, scene_asset_id: value })} />
      </div>
      <div className="docx-actions">
        <button className="primary" disabled={!ready || busy} onClick={preview}>
          <FileImage size={16} />
          预览 9 张提示词
        </button>
        <button className="primary" disabled={(!ready && !activeRun) || busy} onClick={generate}>
          <Sparkles size={16} />
          一键生成 9 张图
        </button>
        <button disabled={!docxRunReadyToDownload(activeRun) || busy} onClick={downloadRun}>
          一键下载 9 张图
        </button>
      </div>
      <div className="run-list docx-run-list">
        {(runs || []).map((run) => (
          <button key={run.id} onClick={() => loadRun(run.id)}>
            <strong>{run.product_name}</strong>
            <span>{run.status} · {run.created_at}</span>
          </button>
        ))}
      </div>
      {activeRun ? (
        <div className="docx-preview">
          <div className="prompt-head">
            <strong>{activeRun.product_name} / {activeRun.material}</strong>
            <span>{activeRun.status}</span>
          </div>
          <div className="workflow-step-grid">
            {(activeRun.steps || []).map((step) => (
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
                <div className="step-rag-refs">
                  <strong>知识库参考：</strong>
                  {(step.reference_items || []).filter((item) => item.type === "rag").length ? (
                    (step.reference_items || []).filter((item) => item.type === "rag").map((item) => (
                      <div key={item.id} className="step-rag-ref-item">
                        {item.url ? <img src={`${API}${item.url}`} alt={item.label} className="step-rag-thumb clickable-img" onClick={() => setPreviewImage({ src: `${API}${item.url}`, alt: item.label })} /> : null}
                        <div className="step-rag-ref-text">
                          <span>图{item.input_image_no} {item.label}</span>
                          {item.usage_labels?.length ? <small>用途：{item.usage_labels.join("、")}</small> : null}
                          {item.model_description ? <small>说明：{item.model_description}</small> : null}
                        </div>
                        <button className="icon-btn danger" title="从本图移除" onClick={() => removeRagRefFromStep(step, item.id)}>
                          <X size={12} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <span className="muted">无</span>
                  )}
                </div>
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

export default function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const projectList = await request("/api/projects");
      setProjects(projectList);
      if (selectedProject) {
        setProjectDetail(await request(`/api/projects/${selectedProject.id}`));
      }
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!selectedProject) return;
    request(`/api/projects/${selectedProject.id}`).then(setProjectDetail).catch((err) => setError(err.message));
  }, [selectedProject]);

  const createProject = async (form) => {
    const project = await request("/api/projects", { method: "POST", body: JSON.stringify(form) });
    setSelectedProject(project);
    await load();
  };
  const deleteProject = async (id) => {
    if (!confirm("确认删除该项目？所有相关素材和记录都会被删除。")) return;
    await request(`/api/projects/${id}`, { method: "DELETE" });
    if (selectedProject?.id === id) setSelectedProject(null);
    await load();
  };

  const assets = projectDetail?.assets || [];
  const docxRuns = projectDetail?.docx_workflow_runs || [];

  return (
    <div className="app-shell">
      <header>
        <div>
          <h1>DOCX 固定九图自动化生图流程</h1>
          <p>上传产品图、模特参考图、上身效果参考图和场景风格参考图，按固定流程生成 9 张商品图。</p>
        </div>
        <div className="status-pill">{selectedProject ? selectedProject.sku : "未选择项目"}</div>
      </header>
      {error ? <div className="error-banner">{error}</div> : null}
      <main>
        <aside>
          <ProjectPanel projects={projects} selectedProject={selectedProject} setSelectedProject={setSelectedProject} onCreate={createProject} onDelete={deleteProject} />
        </aside>
        <div className="workspace">
          {selectedProject && projectDetail ? (
            <>
              <AssetPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
              <RagKnowledgeWorkbench project={selectedProject} refreshProject={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
              <DocxWorkflowPanel project={selectedProject} assets={assets} runs={docxRuns} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
            </>
          ) : (
            <section className="empty-state">先创建或选择一个项目。</section>
          )}
        </div>
      </main>
    </div>
  );
}
