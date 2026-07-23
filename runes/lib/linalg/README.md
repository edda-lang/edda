# linalg

`f64` linear algebra for graphics — 2D/3D vectors, 4×4 matrices, and
quaternions, with the transforms a renderer needs (`translate` / `scale` /
`rotate`, `perspective`, `look_at`). Every operation is pure: no allocator, no
effect row.

## Install

```
edda add linalg
```

Then import the module you need:

```edda
import linalg.vec3
import linalg.mat4
```

## Usage

```edda
import linalg.vec3
import linalg.mat4

function camera(eye: vec3.Vec3, target: vec3.Vec3) -> mat4.Mat4 {
    let up = vec3.vec3(0.0, 1.0, 0.0)
    let view = mat4.look_at(eye, target, up)
    let proj = mat4.perspective(1.047, 1.777, 0.1, 100.0)
    return mat4.mul(proj, view)
}
```

`mat4.mul` composes transforms; `mat4.identity` / `translate` / `scale` /
`rotate` build them. Vectors carry the usual `add` / `sub` / `scale` / `dot` /
`cross` / `normalize` / `length`, and `quat` provides `from_axis_angle`, `mul`,
`slerp`, and `to_mat4` for rotation.

## Public surface

- **`vec2`** — `Vec2`, `vec2` / `zero` / `splat`, `add` / `sub` / `scale` /
  `dot` / `perp_dot` / `length` / `normalize` / `lerp` / `distance`.
- **`vec3`** — `Vec3`, `vec3` / `zero` / `splat`, `add` / `sub` / `scale` /
  `dot` / `cross` / `length` / `normalize` / `lerp` / `distance`.
- **`mat4`** — `Mat4`, `identity` / `mul` / `translate` / `scale` / `rotate` /
  `perspective` / `look_at`.
- **`quat`** — `Quat`, `identity` / `dot` / `length` / `normalize` /
  `from_axis_angle` / `mul` / `slerp` / `to_mat4`.
