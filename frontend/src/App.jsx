import {
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  Brain,
  Database,
  FileImage,
  FlaskConical,
  ImagePlus,
  Layers3,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

const API = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const OUTPUT_TYPES = [
  ["output_a", "OUTPUT-A", "商品事实"],
  ["output_c", "OUTPUT-C", "竞品单图结构"],
  ["output_d", "OUTPUT-D", "类目视觉规范"],
];

const FIELD_TYPES = [
  ["text", "文本"],
  ["textarea", "长文本"],
  ["single_select", "单选"],
  ["multi_select", "多选"],
  ["number", "数字"],
  ["boolean", "开关"],
  ["image_ref", "图片引用"],
  ["list", "列表"],
];

const ASSET_TYPE_LABELS = {
  product: "商品",
  model: "模特",
  competitor: "竞品",
};

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

function emptyValue(type) {
  if (type === "list" || type === "multi_select" || type === "image_ref") return [];
  if (type === "boolean") return false;
  if (type === "number") return 0;
  return "";
}

function FieldInput({ field, value, onChange }) {
  const type = field.type || "text";
  if (type === "textarea") {
    return <textarea value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder={field.help_text || field.label} />;
  }
  if (type === "boolean") {
    return (
      <label className="toggle-line">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        <span>{Boolean(value) ? "是" : "否"}</span>
      </label>
    );
  }
  if (type === "single_select") {
    return (
      <select value={value || ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">未选择</option>
        {(field.options || []).map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    );
  }
  if (type === "multi_select") {
    const selected = Array.isArray(value) ? value : [];
    return (
      <div className="check-grid">
        {(field.options || []).map((option) => (
          <label key={option}>
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={(e) => {
                onChange(e.target.checked ? [...selected, option] : selected.filter((item) => item !== option));
              }}
            />
            {option}
          </label>
        ))}
      </div>
    );
  }
  if (type === "list") {
    return (
      <textarea
        value={Array.isArray(value) ? value.join("\n") : value || ""}
        onChange={(e) => onChange(e.target.value.split("\n").map((line) => line.trim()).filter(Boolean))}
        placeholder="每行一项"
      />
    );
  }
  return <input type={type === "number" ? "number" : "text"} value={value ?? ""} onChange={(e) => onChange(type === "number" ? Number(e.target.value) : e.target.value)} />;
}

function SchemaBuilder({ schemas, activeType, setActiveType, onSchemaSaved }) {
  const schema = schemas[activeType];
  const [draft, setDraft] = useState(schema);

  useEffect(() => setDraft(schema), [schema]);
  if (!draft) return null;

  const updateField = (index, patch) => {
    const fields = [...draft.fields];
    fields[index] = { ...fields[index], ...patch };
    setDraft({ ...draft, fields });
  };
  const moveField = (index, direction) => {
    const next = index + direction;
    if (next < 0 || next >= draft.fields.length) return;
    const fields = [...draft.fields];
    [fields[index], fields[next]] = [fields[next], fields[index]];
    setDraft({ ...draft, fields });
  };

  return (
    <section className="panel">
      <div className="section-title">
        <Layers3 size={18} />
        <h2>字段配置器</h2>
      </div>
      <div className="segmented">
        {OUTPUT_TYPES.map(([type, code, label]) => (
          <button key={type} className={activeType === type ? "active" : ""} onClick={() => setActiveType(type)}>
            {code} · {label}
          </button>
        ))}
      </div>
      <div className="schema-head">
        <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <button className="primary" onClick={() => onSchemaSaved(activeType, draft)}>
          <Save size={16} />
          保存字段版本
        </button>
      </div>
      <div className="field-list">
        {draft.fields.map((field, index) => (
          <div className="field-row" key={`${field.key}-${index}`}>
            <input title="字段key" value={field.key} onChange={(e) => updateField(index, { key: e.target.value })} />
            <input title="显示名称" value={field.label} onChange={(e) => updateField(index, { label: e.target.value })} />
            <select value={field.type} onChange={(e) => updateField(index, { type: e.target.value })}>
              {FIELD_TYPES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <label className="mini-check">
              <input type="checkbox" checked={Boolean(field.required)} onChange={(e) => updateField(index, { required: e.target.checked })} />
              必填
            </label>
            <input title="字段说明" value={field.help_text || ""} onChange={(e) => updateField(index, { help_text: e.target.value })} placeholder="字段说明" />
            <input
              title="选项"
              value={(field.options || []).join(",")}
              onChange={(e) => updateField(index, { options: e.target.value.split(",").map((item) => item.trim()).filter(Boolean) })}
              placeholder="选项用逗号分隔"
            />
            <button title="上移" onClick={() => moveField(index, -1)}>
              <ArrowUp size={15} />
            </button>
            <button title="下移" onClick={() => moveField(index, 1)}>
              <ArrowDown size={15} />
            </button>
            <button title="删除" onClick={() => setDraft({ ...draft, fields: draft.fields.filter((_, i) => i !== index) })}>
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      <button
        className="ghost"
        onClick={() =>
          setDraft({
            ...draft,
            fields: [
              ...draft.fields,
              { key: `field_${draft.fields.length + 1}`, label: "新字段", type: "text", required: false, help_text: "", options: [], prompt_role: "", validation_rule: "", knowledge_enabled: true },
            ],
          })
        }
      >
        <Plus size={16} />
        添加字段
      </button>
    </section>
  );
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

function OutputAEditor({ schema, project, refresh }) {
  const [values, setValues] = useState({});
  if (!schema) return null;
  const save = async () => {
    await request("/api/outputs/product-facts", {
      method: "POST",
      body: JSON.stringify({ project_id: project.id, values }),
    });
    await refresh();
  };
  return (
    <section className="panel">
      <div className="section-title">
        <BadgeCheck size={18} />
        <h2>OUTPUT-A 填写</h2>
      </div>
      <div className="output-grid">
        {schema.fields.map((field) => (
          <label key={field.key} className={field.type === "textarea" || field.type === "list" ? "span2" : ""}>
            <span>
              {field.label}
              {field.required ? <b>*</b> : null}
            </span>
            <FieldInput field={field} value={values[field.key] ?? emptyValue(field.type)} onChange={(value) => setValues({ ...values, [field.key]: value })} />
          </label>
        ))}
      </div>
      <button className="primary" onClick={save}>
        <Save size={16} />
        保存 OUTPUT-A
      </button>
    </section>
  );
}

function AnalysisPanel({ project, assets, outputs, refresh }) {
  const competitorAssets = assets.filter((asset) => asset.asset_type === "competitor");
  const outputC = outputs.filter((item) => item.output_type === "output_c");
  const confirmedC = outputC.filter((item) => item.status === "confirmed");
  const outputD = outputs.filter((item) => item.output_type === "output_d");
  const [selectedAsset, setSelectedAsset] = useState("");
  const [selectedC, setSelectedC] = useState([]);
  const [editing, setEditing] = useState(null);
  const [editingText, setEditingText] = useState("");

  const analyzeImage = async () => {
    await request("/api/analysis/competitor-image", {
      method: "POST",
      body: JSON.stringify({ project_id: project.id, asset_id: selectedAsset }),
    });
    await refresh();
  };
  const analyzeCategory = async () => {
    await request("/api/analysis/category-standard", {
      method: "POST",
      body: JSON.stringify({ project_id: project.id, competitor_output_ids: selectedC }),
    });
    await refresh();
  };
  const saveOutput = async () => {
    let parsed = {};
    try {
      parsed = JSON.parse(editingText || "{}");
    } catch {
      window.alert("JSON 格式不正确，请修正后再保存。");
      return;
    }
    await request(`/api/outputs/${editing.id}`, {
      method: "PATCH",
      body: JSON.stringify({ values: parsed, status: "confirmed", notes: editing.notes || "" }),
    });
    setEditing(null);
    await refresh();
  };

  return (
    <section className="panel">
      <div className="section-title">
        <Brain size={18} />
        <h2>竞品分析</h2>
      </div>
      <div className="analysis-actions">
        <select value={selectedAsset} onChange={(e) => setSelectedAsset(e.target.value)}>
          <option value="">选择一张竞品图</option>
          {competitorAssets.map((asset) => (
            <option key={asset.id} value={asset.id}>
              {asset.original_name}
            </option>
          ))}
        </select>
        <button className="primary" disabled={!selectedAsset} onClick={analyzeImage}>
          <Sparkles size={16} />
          生成 OUTPUT-C
        </button>
      </div>
      <div className="records">
        {outputC.map((item) => (
            <button
              key={item.id}
              className={item.status === "confirmed" ? "record confirmed" : "record"}
              onClick={() => {
                setEditing(item);
                setEditingText(JSON.stringify(item.values, null, 2));
              }}
            >
            <span>{item.status === "confirmed" ? "已确认" : "待确认"}</span>
            <strong>OUTPUT-C</strong>
            <small>{Object.values(item.values || {}).slice(0, 2).join(" / ")}</small>
          </button>
        ))}
      </div>
      <div className="analysis-actions">
        <select multiple value={selectedC} onChange={(e) => setSelectedC([...e.target.selectedOptions].map((option) => option.value))}>
          {confirmedC.map((item) => (
            <option key={item.id} value={item.id}>
              {item.id.slice(0, 8)} · {Object.values(item.values || {}).slice(0, 2).join(" / ")}
            </option>
          ))}
        </select>
        <button className="primary" disabled={!selectedC.length} onClick={analyzeCategory}>
          <Database size={16} />
          生成 OUTPUT-D
        </button>
      </div>
      <div className="records">
        {outputD.map((item) => (
          <button
            key={item.id}
            className={item.status === "confirmed" ? "record confirmed" : "record"}
            onClick={() => {
              setEditing(item);
              setEditingText(JSON.stringify(item.values, null, 2));
            }}
          >
            <span>{item.status === "confirmed" ? "已确认" : "待确认"}</span>
            <strong>OUTPUT-D</strong>
            <small>{Object.keys(item.values || {}).join(", ")}</small>
          </button>
        ))}
      </div>
      {editing && (
        <div className="modal-backdrop">
          <div className="modal">
            <h3>确认 {editing.output_type === "output_c" ? "OUTPUT-C" : "OUTPUT-D"}</h3>
            <textarea className="json-editor" value={editingText} onChange={(e) => setEditingText(e.target.value)} />
            <div className="modal-actions">
              <button onClick={() => setEditing(null)}>取消</button>
              <button className="primary" onClick={saveOutput}>
                <Save size={16} />
                确认保存
              </button>
            </div>
          </div>
        </div>
      )}
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
                {step.url ? <img src={`${API}${step.url}`} alt={step.title} /> : <div className="step-placeholder">{step.error || "等待生成"}</div>}
                <textarea
                  value={promptDrafts[step.id] ?? step.prompt ?? ""}
                  onChange={(event) => setPromptDrafts({ ...promptDrafts, [step.id]: event.target.value })}
                />
                <div className="docx-actions">
                  <button onClick={() => savePrompt(step.id, promptDrafts[step.id] ?? step.prompt ?? "")}>保存提示词</button>
                  <button onClick={() => regenerateStep(step.id)} disabled={busy}>重新生成本张</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function GenerationPanel({ project, assets, outputs, runs, refresh }) {
  const productAssets = assets.filter((asset) => asset.asset_type === "product");
  const modelAssets = assets.filter((asset) => asset.asset_type === "model");
  const competitorAssets = assets.filter((asset) => asset.asset_type === "competitor");
  const confirmedC = outputs.filter((item) => item.output_type === "output_c" && item.status === "confirmed");
  const hasA = outputs.some((item) => item.output_type === "output_a" && item.status === "confirmed");
  const hasD = outputs.some((item) => item.output_type === "output_d" && item.status === "confirmed");
  const [form, setForm] = useState({ title: "", image_goal: "", supplemental_info: "", product_asset_ids: [], model_asset_ids: [], competitor_asset_ids: [], competitor_output_ids: [] });
  const [activeRun, setActiveRun] = useState(null);
  const [results, setResults] = useState([]);

  const toggle = (key, id) => {
    const current = form[key] || [];
    setForm({ ...form, [key]: current.includes(id) ? current.filter((item) => item !== id) : [...current, id] });
  };
  const createRun = async () => {
    const run = await request("/api/generation-runs", { method: "POST", body: JSON.stringify({ project_id: project.id, ...form }) });
    setActiveRun(run);
    await refresh();
  };
  const generate = async () => {
    if (!activeRun) return;
    await request(`/api/generation-runs/${activeRun.id}/generate`, { method: "POST", body: JSON.stringify({ size: "1024x1024", quality: "high" }) });
    await loadResults(activeRun.id);
    await refresh();
  };
  const loadResults = async (runId) => {
    setResults(await request(`/api/generation-runs/${runId}/results`));
  };
  const markCandidate = async (result) => {
    await request(`/api/generation-results/${result.id}/review`, {
      method: "POST",
      body: JSON.stringify({ rating: 5, review_notes: "设计部标记为优秀实验", is_knowledge_candidate: true }),
    });
    await loadResults(activeRun.id);
  };
  const deleteAsset = async (id) => {
    if (!confirm("确认删除这张图片？")) return;
    await request(`/api/assets/${id}`, { method: "DELETE" });
    await refresh();
  };

  return (
    <section className="panel">
      <div className="section-title">
        <Sparkles size={18} />
        <h2>单张生图实验</h2>
      </div>
      {!hasA || !hasD ? <div className="notice">需要已确认的 OUTPUT-A 和 OUTPUT-D 后才能创建生图实验。</div> : null}
      <div className="generation-grid">
        <input placeholder="实验标题" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <textarea placeholder="图片目标，例如主图、面料细节图、支撑卖点图" value={form.image_goal} onChange={(e) => setForm({ ...form, image_goal: e.target.value })} />
        <textarea placeholder="无法结构化的补充信息" value={form.supplemental_info} onChange={(e) => setForm({ ...form, supplemental_info: e.target.value })} />
      </div>
      <AssetPicker title="商品参考图" assets={productAssets} selected={form.product_asset_ids} onToggle={(id) => toggle("product_asset_ids", id)} onDelete={deleteAsset} />
      <AssetPicker title="模特参考图" assets={modelAssets} selected={form.model_asset_ids} onToggle={(id) => toggle("model_asset_ids", id)} onDelete={deleteAsset} />
      <AssetPicker title="竞品图留痕" assets={competitorAssets} selected={form.competitor_asset_ids} onToggle={(id) => toggle("competitor_asset_ids", id)} onDelete={deleteAsset} />
      <div className="check-grid outputs">
        {confirmedC.map((item) => (
          <label key={item.id}>
            <input type="checkbox" checked={form.competitor_output_ids.includes(item.id)} onChange={() => toggle("competitor_output_ids", item.id)} />
            OUTPUT-C {item.id.slice(0, 8)}
          </label>
        ))}
      </div>
      <button className="primary" disabled={!hasA || !hasD} onClick={createRun}>
        <FileImage size={16} />
        生成提示词实验
      </button>
      {activeRun && (
        <div className="prompt-box">
          <div className="prompt-head">
            <strong>{activeRun.title}</strong>
            <button className="primary" onClick={generate}>
              <Sparkles size={16} />
              调用 Image2 生图
            </button>
          </div>
          <pre>{activeRun.prompt}</pre>
        </div>
      )}
      <div className="run-list">
        {runs.map((run) => (
          <button
            key={run.id}
            onClick={async () => {
              setActiveRun(run);
              await loadResults(run.id);
            }}
          >
            <strong>{run.title}</strong>
            <span>{run.status}</span>
          </button>
        ))}
      </div>
      <div className="result-grid">
        {results.map((result) => (
          <article className="result-card" key={result.id}>
            {result.url ? <img src={`${API}${result.url}`} alt="generated" /> : <div className="error">{result.error}</div>}
            <button onClick={() => markCandidate(result)}>
              <Database size={15} />
              标记为知识库候选
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

function AssetPicker({ title, assets, selected, onToggle, onDelete }) {
  return (
    <div className="picker">
      <h3>{title}</h3>
      <div className="asset-pick-list">
        {assets.map((asset) => (
          <div key={asset.id} className={selected.includes(asset.id) ? "pick-item picked" : "pick-item"}>
            <button className="pick-main" onClick={() => onToggle(asset.id)}>
              {asset.url ? (
                <img src={`${API}${asset.url}`} alt={asset.original_name} />
              ) : (
                <div className="asset-missing">文件缺失<br />请删除后重新上传</div>
              )}
              <span>{asset.original_name}</span>
            </button>
            {onDelete && (
              <button className="icon-btn danger pick-del" title="删除" onClick={(e) => { e.stopPropagation(); onDelete(asset.id); }}>
                <Trash2 size={12} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [projectDetail, setProjectDetail] = useState(null);
  const [schemas, setSchemas] = useState({});
  const [activeSchemaType, setActiveSchemaType] = useState("output_a");
  const [knowledge, setKnowledge] = useState([]);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const [projectList, schemaA, schemaC, schemaD, candidates] = await Promise.all([
        request("/api/projects"),
        request("/api/schemas/output_a"),
        request("/api/schemas/output_c"),
        request("/api/schemas/output_d"),
        request("/api/knowledge-candidates"),
      ]);
      setProjects(projectList);
      setSchemas({ output_a: schemaA, output_c: schemaC, output_d: schemaD });
      setKnowledge(candidates);
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
  const saveSchema = async (type, schema) => {
    const saved = await request(`/api/schemas/${type}`, { method: "POST", body: JSON.stringify({ name: schema.name, fields: schema.fields }) });
    setSchemas({ ...schemas, [type]: saved });
  };

  const assets = projectDetail?.assets || [];
  const outputs = projectDetail?.outputs || [];
  const runs = projectDetail?.runs || [];
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
          <section className="panel compact">
            <div className="section-title">
              <Database size={18} />
              <h2>知识库候选</h2>
            </div>
            <div className="candidate-list">
              {knowledge.map((item) => (
                <div key={item.id}>
                  <strong>{item.status}</strong>
                  <span>{item.created_at}</span>
                </div>
              ))}
            </div>
          </section>
        </aside>
        <div className="workspace">
          {selectedProject && projectDetail ? (
            <>
              <AssetPanel project={selectedProject} assets={assets} refresh={() => request(`/api/projects/${selectedProject.id}`).then(setProjectDetail)} />
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
