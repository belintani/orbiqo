# Linear tessellation criteria

The Draft 0.3 layout intentionally changes both sector count and fractional phase between neighboring rings. This avoids long radial seams, but it creates the visual effect identified by the project owner: cell ends appear to interlock or overlap, and the payload reads as scales rather than as deliberate radial columns.

The redesign compares four structures. **Current** preserves sector-dependent phase offsets. **Linear phase** keeps every current sector count but starts every ring at the same twelve-o’clock boundary. **Terraced** is the partial hierarchical alternative: inner columns remain aligned and split once into exactly two aligned outer columns. **Columns** gives every ring the same sector count as the innermost data ring, creating fully continuous spokes but reducing capacity and changing the physical address map.

| Criterion | Preferred direction |
| --- | --- |
| Boundary alignment rate | Higher |
| Mean normalized boundary discontinuity | Lower |
| Apparent overlap at adjacent rings | Lower |
| Exact clean decode | 100% required for an implementation candidate |
| Capacity under equal area | Must remain competitive with tested QR/Aztec profiles |
| Draft compatibility | Renderer-only changes preferred; address-map changes require Draft 0.4 |

The first contact sheet is intentionally rendered with the Reference fill profile rather than Pulse. This isolates tessellation from the denser visual skin. Constant Columns is a visual-only prototype until a new encoder/decoder map exists; it must not be presented as interoperable Draft 0.3 output.

## Measured result

Draft 0.3 aligns only **2.45–2.93%** of adjacent-ring boundaries across Small–XL. Its mean normalized boundary discontinuity is approximately **0.27–0.28 cell widths**, which explains the visible scale/interlock effect. Starting every ring at twelve o’clock without changing sector counts increases exact boundary alignment to **24.18–27.27%** and lowers mean discontinuity to approximately **0.19–0.20**, while preserving every cell and byte of capacity.

Terraced and constant Columns reach **100% boundary alignment** because every outer boundary nests on an inner spoke. Terraced retains almost all cells: 1,064 versus 1,104 in Small; 2,464 versus 2,480 in Medium; 4,368 versus 4,400 in Large; and 6,664 versus 6,872 in XL. Constant Columns falls to 672, 1,584, 2,688, and 4,080 cells respectively.

The end-to-end experiment patched encoder, mask layout, decoder, and geometry consistently for each candidate. All four variants decoded exactly in clean, blur 1.2, JPEG 55, downsample 0.55, and noise sigma 7 across all four geometry sizes. Phase Linear preserved the exact Draft 0.3 capacity: 183, 410, 762, and 1,252 bytes. Terraced produced 183, 406, 756, and 1,200 bytes. Constant Columns fell to 86, 250, 462, and 746 bytes.
