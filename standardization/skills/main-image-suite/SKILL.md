---
name: main-image-suite
description: Plan, generate, track, refine, and download consistent nine-image product suites. Use when an Agent needs to retrieve reference images from the image knowledge base, create a product project, upload product and reference assets, initialize the fixed nine-image workflow, preserve model-garment-scene consistency, regenerate individual images, or add approved generated images back to the knowledge base.
---

# 商品九图生成

## Overview

Use the image knowledge-base MCP to retrieve suitable references and the main-image task MCP to run the existing fixed nine-image workflow. Do not duplicate backend prompt logic or call image models directly.

Read [references/api-guide.md](references/api-guide.md) when preparing tool arguments or diagnosing a failed request.

## Workflow

### 1. Confirm the product project

Collect:

- SKU or project identifier
- Product name and material
- Product image
- Model reference image when available
- Front, side, and back fit references when available
- Scene-style reference when available
- Accessory or outfit reference

Create the project with `create_main_image_project`.

### 2. Retrieve knowledge-base references

Use `search_knowledge_images` for text-based searches such as:

- model identity reference
- scene and photography-style reference
- pose reference
- accessory or outfit reference

Use `search_knowledge_images_by_image` when the user already has one reference image and wants similar options.

Review candidate results before adding them to the project. Use `add_rag_reference_to_project` to record selected references and `copy_rag_reference_to_project_asset` when the workflow needs a local project asset.

### 3. Upload project assets

Call `upload_project_assets` with absolute paths. Keep the purpose of each image explicit:

- Product image: defines product structure, color, texture, and details.
- Model reference: defines final person identity and body characteristics.
- Fit references: define front, side, and back wearing states.
- Scene reference: defines background, framing, atmosphere, and photography style.
- Accessory reference: defines outfit accessories for the styling image.

### 4. Plan the nine-image suite

Use `initialize_nine_image_workflow`. The existing service owns the fixed plan:

1. Model wearing product
2. Scene model image
3. Front angle image
4. Side angle image
5. Back angle image
6. Additional angle image
7. Outfit styling image
8. White-background main image
9. White-background back image

Do not replace this structure unless the user explicitly requests a workflow redesign.

### 5. Protect reference boundaries

Apply these rules when reviewing the initialized workflow or explaining requirements:

- Product references may define garment color, material, cut, and construction details.
- Model references may define identity, face, hair, body shape, and skin tone.
- Scene references may define background, composition, mood, lighting, and photography style.
- Pose references may define pose and expression only.
- Accessory references may define styling accessories only.

Do not copy unrelated people, clothing, logos, text, watermarks, or branded elements from references.

### 6. Preserve suite consistency

Across all nine images:

- Keep the same model identity unless the user explicitly requests a change.
- Keep product color, material, silhouette, stitching, and design details stable.
- Keep scene lighting and photography style coherent.
- Avoid extra people, duplicated limbs, blocked product details, collage layouts, text, logos, and watermarks.

The existing backend prompt templates already express these rules. Do not rebuild them in the Agent layer.

### 7. Generate and track results

Call `generate_nine_image_suite`, then poll `get_nine_image_workflow`.

- If images are pending or running, report progress and check again later.
- If one image fails, report the failed step and use `regenerate_nine_image_step` after checking its references.
- If one image is unsatisfactory, regenerate only that step.
- When all nine images are ready, call `download_nine_image_suite`.

Keep `overwrite=false` unless the user explicitly allows replacing an existing ZIP file.

### 8. Add approved results to the knowledge base

When the user identifies an excellent generated image worth reusing, call `add_knowledge_image`. Add meaningful category, scene, image type, asset type, and metadata so future searches can retrieve it.

## Guardrails

- Do not modify the existing main-image backend, frontend, RAG backend, or prompt templates while executing this Skill.
- Do not assume the main-image service is running. Report a clear service-unavailable error if it cannot be reached.
- Do not overwrite an existing ZIP result without explicit permission.
- Do not write directly to the RAG database or vector store.
- Do not add generated images to the knowledge base without user approval.
