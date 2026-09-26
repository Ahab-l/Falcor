# Native GBuffer comparison: precise-world-position

Native NPZ SHA-256: `7ebee38e1c79995a8292517627c917d32a26baf9539983b46e57a1f7bdb8c626`. All capture files passed their recorded uncompressed byte/hash checks.

This report compares captured EID 1853 physical attachments. It does not assert final shaded-image equality.

Extent 1424×1040; ViewRect 1421×1035. Coverage mismatch: **0** pixels. Depth outliers above 1e-6: **0**. Exact coordinates are retained in the JSON.

| Scope | Pixels | A normal RGB exact | A alpha exact | B exact | C exact | Model bits exact |
|---|---:|---:|---:|---:|---:|---:|
| full_extent | 1480960 | 1480959 | 1480960 | 1480955 | 1480960 | 1480960 |
| covered_overlap | 866712 | 866711 | 866712 | 866707 | 866712 | 866712 |
| sphere_interior | 49956 | 49955 | 49956 | 49956 | 49956 | 49956 |
| cube_interior | 70568 | 70568 | 70568 | 70568 | 70568 | 70568 |
| standing_plane_interior | 169867 | 169867 | 169867 | 169867 | 169867 | 169867 |
| grid_floor_interior | 557948 | 557948 | 557948 | 557943 | 557948 | 557948 |

Object interiors exclude a 2-pixel square radius around the independently reconstructed CPU object-ID boundaries. Full extent, ViewRect, background, full object-ID regions and interiors are all reported separately.

The JSON includes signed integer error histograms, mean/p99/p999/max component errors, one/two-LSB exceedance counts, RGBA half values and raw half-bit comparisons, decoded sRGB linear errors, low-five shading-model bits (mask31) and high-three selective-output flags (mask224), matching this customized UE Schema. Normal comparisons use 2/1023 per stored 10-bit step; no tolerance is silently treated as equality.

GBufferD exact over full extent: **True**. SceneColor half bits exact over full extent: **False**.

Difference images and capture/native baseColor previews: `E:\Project\falcor\Falcor-m0\build\rdc-scene\native-precise-world-position`.

Native stencil is compared over the whole allocation: **0** mismatched pixels.
Native depth-plane bits match capture over the whole allocation: **True**.
A small raw packed-word difference is not a normal tolerance; A is also compared component-by-component.
