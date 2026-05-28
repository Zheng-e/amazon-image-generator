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
  pose_reference: ["competitor"],
  accessory_reference: ["competitor"],
};

const DOCX_SLOT_LABELS = {
  product_image: "产品图",
  model_reference: "模特参考",
  fit_reference: "上身效果参考",
  scene_style_reference: "场景风格参考",
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

function DocxWorkflowPanel({ project, assets, refresh, onDownload }) {
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
    fit_front_asset_id: "",
    fit_side_asset_id: "",
    fit_back_asset_id: "",
    scene_asset_id: "",
    accessory_asset_id: "",
  });
  const [workflow, setWorkflow] = useState(null);
  const [promptDrafts, setPromptDrafts] = useState({});
  const [busy, setBusy] = useState(false);
  const [previewImage, setPreviewImage] = useState(null);
  const productFileRef = useRef(null);
  const modelFileRef = useRef(null);
  const fitFrontFileRef = useRef(null);
  const fitSideFileRef = useRef(null);
  const fitBackFileRef = useRef(null);
  const sceneFileRef = useRef(null);
  const accessoryFileRef = useRef(null);
  const poseFileRef = useRef(null);

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
      fit_front_asset_id: current.fit_front_asset_id || workflow.fit_front_asset_id || "",
      fit_side_asset_id: current.fit_side_asset_id || workflow.fit_side_asset_id || "",
      fit_back_asset_id: current.fit_back_asset_id || workflow.fit_back_asset_id || "",
      scene_asset_id: current.scene_asset_id || workflow.scene_asset_id || "",
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
    form.fit_front_asset_id &&
    form.fit_side_asset_id &&
    form.fit_back_asset_id &&
    form.scene_asset_id;

  const initWorkflow = async () => {
    return request(`/api/projects/${project.id}/workflow`, {
      method: "POST",
      body: JSON.stringify({ ...form, project_id: project.id }),
    });
  };

  const uploadOne = async (ref, assetType, slot, notes) => {
    const file = ref.current?.files?.[0];
    if (!file) return "";
    const id = await uploadOneFile(file, assetType, slot, notes);
    ref.current.value = "";
    return id;
  };

  const uploadOneFile = async (file, assetType, slot, notes) => {
    const data = new FormData();
    data.append("project_id", project.id);
    data.append("asset_type", assetType);
    data.append("slot", slot);
    data.append("notes", notes);
    data.append("files", file);
    const uploaded = await request("/api/assets", { method: "POST", body: data });
    return uploaded[0]?.id || "";
  };

  const uploadRequiredAssets = async () => {
    setBusy(true);
    try {
      const [productId, modelId, fitFrontId, fitSideId, fitBackId, sceneId, accessoryId] = await Promise.all([
        uploadOne(productFileRef, "product", "product_image", "固定九图流程：产品图"),
        uploadOne(modelFileRef, "model", "model_reference", "固定九图流程：模特面部及身材参考图"),
        uploadOne(fitFrontFileRef, "competitor", "fit_front_reference", "固定九图流程：衣服上身效果正面参考图"),
        uploadOne(fitSideFileRef, "competitor", "fit_side_reference", "固定九图流程：衣服上身效果侧面参考图"),
        uploadOne(fitBackFileRef, "competitor", "fit_back_reference", "固定九图流程：衣服上身效果背面参考图"),
        uploadOne(sceneFileRef, "competitor", "scene_style_reference", "固定九图流程：场景风格参考图"),
        uploadOne(accessoryFileRef, "competitor", "accessory_reference", "固定九图流程：配饰参考图"),
      ]);
      setForm((current) => ({
        ...current,
        product_asset_id: productId || current.product_asset_id,
        model_asset_id: modelId || current.model_asset_id,
        fit_front_asset_id: fitFrontId || current.fit_front_asset_id,
        fit_side_asset_id: fitSideId || current.fit_side_asset_id,
        fit_back_asset_id: fitBackId || current.fit_back_asset_id,
        scene_asset_id: sceneId || current.scene_asset_id,
        accessory_asset_id: accessoryId || current.accessory_asset_id,
      }));
      // Upload pose reference images (multiple files)
      const poseFiles = poseFileRef.current?.files;
      if (poseFiles?.length) {
        for (let i = 0; i < poseFiles.length; i++) {
          await uploadOneFile(poseFiles[i], "competitor", "pose_reference", "固定九图流程：姿势参考图");
        }
        poseFileRef.current.value = "";
      }
      if (productId || modelId || fitFrontId || fitSideId || fitBackId || sceneId || accessoryId || (poseFiles?.length)) {
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

  const removeRagRefFromStep = async (step, ragRefId) => {
    const currentRefs = step.input_refs || [];
    const newRefs = currentRefs.filter((ref) => !(ref.type === "rag" && ref.id === ragRefId));
    setBusy(true);
    try {
      const updated = await request(`/api/projects/workflow/steps/${step.id}`, {
        method: "PATCH",
        body: JSON.stringify({ input_refs: newRefs }),
      });
      setWorkflow((current) => current ? { ...current, steps: (current.steps || []).map((s) => s.id === step.id ? { ...s, ...updated } : s) } : current);
    } catch (err) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const updateStepPoseRef = async (step, poseAssetId) => {
    const currentRefs = step.input_refs || [];
    const withoutPose = currentRefs.filter((ref) => !(ref.type === "asset" && assets.some((a) => a.id === ref.id && a.slot === "pose_reference")));
    const newRefs = poseAssetId ? [...withoutPose, { type: "asset", id: poseAssetId }] : withoutPose;
    setBusy(true);
    try {
      const updated = await request(`/api/projects/workflow/steps/${step.id}`, {
        method: "PATCH",
        body: JSON.stringify({ input_refs: newRefs }),
      });
      setWorkflow((current) => current ? { ...current, steps: (current.steps || []).map((s) => s.id === step.id ? { ...s, ...updated } : s) } : current);
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
          <span>模特面部及身材参考图</span>
          <input ref={modelFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>衣服上身效果正面参考图</span>
          <input ref={fitFrontFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>衣服上身效果侧面参考图</span>
          <input ref={fitSideFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>衣服上身效果背面参考图</span>
          <input ref={fitBackFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>场景风格参考图</span>
          <input ref={sceneFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>配饰参考图（可选）</span>
          <input ref={accessoryFileRef} type="file" accept="image/*" />
        </label>
        <label className="stacked-field">
          <span>姿势参考图（可选，可多选）</span>
          <input ref={poseFileRef} type="file" accept="image/*" multiple />
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
        <DocxAssetSelect label="模特面部及身材参考图" assets={assets} slotHint="model_reference" value={form.model_asset_id} onChange={(value) => setForm({ ...form, model_asset_id: value })} />
        <DocxAssetSelect label="衣服上身效果正面参考图" assets={assets} slotHint="fit_front_reference" value={form.fit_front_asset_id} onChange={(value) => setForm({ ...form, fit_front_asset_id: value })} />
        <DocxAssetSelect label="衣服上身效果侧面参考图" assets={assets} slotHint="fit_side_reference" value={form.fit_side_asset_id} onChange={(value) => setForm({ ...form, fit_side_asset_id: value })} />
        <DocxAssetSelect label="衣服上身效果背面参考图" assets={assets} slotHint="fit_back_reference" value={form.fit_back_asset_id} onChange={(value) => setForm({ ...form, fit_back_asset_id: value })} />
        <DocxAssetSelect label="场景风格参考图" assets={assets} slotHint="scene_style_reference" value={form.scene_asset_id} onChange={(value) => setForm({ ...form, scene_asset_id: value })} />
        <DocxAssetSelect label="配饰参考图（可选）" assets={assets} slotHint="accessory_reference" value={form.accessory_asset_id} onChange={(value) => { setForm({ ...form, accessory_asset_id: value }); setWorkflow(null); }} />
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
                {(step.reference_items || []).filter((item) => item.type !== "rag").length ? (
                  <div className="step-base-refs">
                    <strong>基础参考：</strong>
                    {(step.reference_items || []).filter((item) => item.type !== "rag").map((item) => (
                      <div key={item.id} className="step-base-ref-item">
                        {item.url ? <img src={`${API}${item.url}`} alt={item.label} className="step-base-ref-thumb clickable-img" onClick={() => setPreviewImage({ src: `${API}${item.url}`, alt: item.label })} /> : null}
                        <div className="step-base-ref-text">
                          <span>图{item.order} {item.label}</span>
                          <small>{item.type === "step" ? `前置步骤 · ${item.status || "待生成"}` : item.slot || item.asset_type || ""}</small>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
                {["angle_3", "angle_4", "angle_5", "angle_6", "white_main", "white_back"].includes(step.stage_id) ? (
                  <div className="step-pose-ref">
                    <strong>姿势参考：</strong>
                    <select
                      value={(step.input_refs || []).find((ref) => ref.type === "asset" && assets.some((a) => a.id === ref.id && a.slot === "pose_reference"))?.id || ""}
                      onChange={(e) => updateStepPoseRef(step, e.target.value)}
                      disabled={busy}
                    >
                      <option value="">无</option>
                      {assets.filter((a) => a.slot === "pose_reference").map((asset) => (
                        <option key={asset.id} value={asset.id}>{asset.original_name}</option>
                      ))}
                    </select>
                  </div>
                ) : null}
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
            <RagKnowledgeWorkbench project={selectedProject} refreshProject={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
            <DocxWorkflowPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} onDownload={() => loadProjects(selectedUser.id)} />
          </div>
        ) : (
          <section className="empty-state">请从左侧选择一个项目。</section>
        )}
      </main>
    </div>
  );
}
