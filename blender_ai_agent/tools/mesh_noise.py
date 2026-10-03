"""
mesh_noise.py
==============
Hinglish: Mesh engine ka noise. Pure Python, bpy nahi. Value-noise (3D) + fBm (kai layer ka noise) + ridged.
Same (x, y, z, seed) hamesha same value deta hai (deterministic), isliye same seed = same result.
"""

import math


def _hash(ix: int, iy: int, iz: int, seed: int) -> float:
    """Integer hash -> [0, 1)."""
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 1274126177) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 4294967296.0


def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def value_noise(x: float, y: float, z: float, seed: int = 0) -> float:
    """Smooth 3D value noise in [-1, 1]."""
    x0, y0, z0 = math.floor(x), math.floor(y), math.floor(z)
    fx, fy, fz = _fade(x - x0), _fade(y - y0), _fade(z - z0)
    ix, iy, iz = int(x0), int(y0), int(z0)

    def corner(dx, dy, dz):
        return _hash(ix + dx, iy + dy, iz + dz, seed)

    c00 = corner(0, 0, 0) * (1 - fx) + corner(1, 0, 0) * fx
    c10 = corner(0, 1, 0) * (1 - fx) + corner(1, 1, 0) * fx
    c01 = corner(0, 0, 1) * (1 - fx) + corner(1, 0, 1) * fx
    c11 = corner(0, 1, 1) * (1 - fx) + corner(1, 1, 1) * fx
    c0 = c00 * (1 - fy) + c10 * fy
    c1 = c01 * (1 - fy) + c11 * fy
    return (c0 * (1 - fz) + c1 * fz) * 2.0 - 1.0


def fbm(x: float, y: float, z: float, octaves: int = 3, lacunarity: float = 2.0, gain: float = 0.5,
        seed: int = 0) -> float:
    """Fractal noise (kai octave) in [-1, 1]."""
    octaves = max(1, min(8, int(octaves)))
    total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
    for octave in range(octaves):
        total += value_noise(x * frequency, y * frequency, z * frequency, seed + octave * 101) * amplitude
        norm += amplitude
        amplitude *= gain
        frequency *= lacunarity
    return total / norm if norm else 0.0


def ridged(x: float, y: float, z: float, octaves: int = 3, seed: int = 0) -> float:
    """Ridged noise in [-1, 1] — pahaad / daraar jaisi tez kinaaron wali lakeerein."""
    return 1.0 - 2.0 * abs(fbm(x, y, z, octaves=octaves, seed=seed))


def rand01(index: int, seed: int = 0) -> float:
    """Index ke liye ek pakka random number [0, 1)."""
    return _hash(int(index), 7, 13, int(seed))