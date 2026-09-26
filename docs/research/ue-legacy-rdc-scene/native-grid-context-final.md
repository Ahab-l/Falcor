# Native GBuffer comparison: grid-context-final

Native NPZ SHA-256: `8b618a55acb63a77bc9d1520e30ae73fa6617adab977c95e543f38e30e3c2d69`. All capture files passed their recorded uncompressed byte/hash checks.

This report compares captured EID 1853 physical attachments. It does not assert final shaded-image equality.

Extent 1424×1040; ViewRect 1421×1035. Coverage mismatch: **0** pixels. Depth outliers above 1e-6: **2**. Exact coordinates are retained in the JSON.

| Scope | Pixels | A normal RGB exact | A alpha exact | B exact | C exact | Model bits exact |
|---|---:|---:|---:|---:|---:|---:|
| full_extent | 1480960 | 1475056 | 1480960 | 1479596 | 1480785 | 1480960 |
| covered_overlap | 866712 | 860808 | 866712 | 865348 | 866537 | 866712 |
| sphere_interior | 49956 | 44232 | 49956 | 49956 | 49956 | 49956 |
| cube_interior | 70568 | 70568 | 70568 | 70568 | 70568 | 70568 |
| standing_plane_interior | 169867 | 169867 | 169867 | 169867 | 169867 | 169867 |
| grid_floor_interior | 557948 | 557948 | 557948 | 556614 | 557780 | 557948 |

Object interiors exclude a 2-pixel square radius around the independently reconstructed CPU object-ID boundaries. Full extent, ViewRect, background, full object-ID regions and interiors are all reported separately.

The JSON includes signed integer error histograms, mean/p99/p999/max component errors, one/two-LSB exceedance counts, RGBA half values and raw half-bit comparisons, decoded sRGB linear errors, low-five shading-model bits (mask31) and high-three selective-output flags (mask224), matching this customized UE Schema. Normal comparisons use 2/1023 per stored 10-bit step; no tolerance is silently treated as equality.

GBufferD exact over full extent: **True**. SceneColor half bits exact over full extent: **False**.

Difference images and capture/native baseColor previews: `E:\Project\falcor\Falcor-m0\build\rdc-scene\native-grid-context-final`.

Native stencil is absent from the NPZ and is not compared. A small raw packed-word difference is not a normal tolerance; A is also compared component-by-component.
