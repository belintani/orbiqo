# Orbiqo visual signature decision

**Selected presentation profile:** Pulse  
**Reference profile retained:** Classic  
**Format compatibility:** RadialCode Draft 0.3 `cell_states` unchanged

Four renderer-only signatures were compared at 30 mm / Small using the same COLOR4 payload and five deterministic digital degradations. No candidate passed all five; the result is therefore recorded as a trade-off, not a hidden visual “improvement.”

| Variant | Angular fill | Radial fill | Exact decodes | Painted fraction | Visual character |
| --- | ---: | ---: | ---: | ---: | --- |
| Classic | 0.88 | 0.72 | 4/5 | 46.5% | Balanced technical baseline |
| Aero | 0.76 | 0.62 | 1/5 | 39.6% | Airy but too fragile |
| Ribbon | 0.94 | 0.68 | 3/5 | 38.8% | Directional and fine-grained |
| **Pulse** | **0.82** | **0.86** | **4/5** | **53.2%** | Bold, dense, unmistakably radial |

Pulse passed clean, blur 1.2, downsample 0.55, and noise sigma 7, but failed the JPEG-55 trial. Classic passed clean, blur, JPEG-55, and downsample, but failed the same noise trial. The 16-profile grid search did not find a five-of-five fill combination; all top candidates retained one failure.

Pulse is selected for the Orbiqo Lab showroom because it turns the payload into a more continuous, vinyl-like field and gives the product a recognizable silhouette at thumbnail size. Classic remains the benchmark and interoperability reference profile. The UI must expose the distinction explicitly: Pulse is a **visual skin**, not a higher-capacity or more robust coding mode.

The center disk, thick guard, visible 64-slot clock, and four asymmetric guard gaps remain the core signature. Future palette work requires a new published palette identifier and cannot silently replace Draft 0.3 colors.

| Element | Final decision | Compatibility reason |
| --- | --- | --- |
| Payload rings | **Pulse** uses 0.82 angular fill and 0.86 radial fill; Reference remains selectable | Renderer-only geometry; encoded `cell_states` do not change |
| Outer guard | Keep the Draft 0.3 black guard and four unequal clear gaps | Guard and gaps are detection and pose infrastructure |
| Center | Keep the white non-functional disk with a short `OQ` mark by default | Preserves the documented logo-safe region |
| Palette | Keep Draft 0.3 COLOR4 cyan, magenta, yellow, and dark state | A new palette requires a new published palette ID and corpus |
| Lab presentation | Pulse is the default showroom skin and is labeled as such in metadata and UI | Avoids presenting a visual skin as a coding advantage |

The Orbiqo Lab now generates both SVG and PNG with the selected skin, returns `visual_style` in the artifact metadata, exposes Reference/Pulse controls, and displays the active skin next to geometry, ECC, and mask. The default preview was visually verified with the Pulse ring field, unchanged guard, unchanged center-safe disk, and unchanged Draft 0.3 palette.

The same grammar now spans the full laboratory. Reader uses concentric cyan/coral inspection rings, the circular guard guide, and a `PULSE FIELD · LOCAL` provenance badge. Benchmarks uses a restrained radial metrology watermark, ring-derived KPI markers, and keeps the coral/cyan channel pair for generation/decode. Create, Reader, and Benchmarks were reviewed as full pages at 1280×900 and 390×844; controls remain readable, the circular motifs do not obscure data, and mobile preserves the same hierarchy without horizontal overflow.
