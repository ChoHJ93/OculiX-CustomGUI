# -*- coding: utf-8 -*-
"""Pixel colour helpers for OculiX (Jython 2.7 / Java AWT Robot).

Design rules enforced here:
  * every wait is bounded by an explicit timeout - no infinite loops
  * polling interval is caller-controlled
  * per-channel RGB tolerance (easier to reason about than a distance metric);
    euclidean_distance() is provided for the cases where it is the better fit
"""

import time
from java.awt import Robot

_robot = None


def _get_robot():
    """Lazily create a single shared Robot instance."""
    global _robot
    if _robot is None:
        _robot = Robot()
    return _robot


def get_pixel_rgb(x, y):
    """Return (r, g, b) of the screen pixel at absolute coordinates (x, y)."""
    c = _get_robot().getPixelColor(int(x), int(y))
    return (c.getRed(), c.getGreen(), c.getBlue())


def _normalise_tolerance(tolerance):
    """Accept either a scalar or a per-channel (tr, tg, tb) tuple."""
    if isinstance(tolerance, (int, long, float)):
        return (tolerance, tolerance, tolerance)
    return tolerance


def is_color_similar(actual, target, tolerance=10):
    """True when every channel of actual is within tolerance of target.

    actual, target : (r, g, b)
    tolerance      : scalar applied to all channels, or (tr, tg, tb)
    """
    tol = _normalise_tolerance(tolerance)
    for i in range(3):
        if abs(int(actual[i]) - int(target[i])) > tol[i]:
            return False
    return True


def euclidean_distance(a, b):
    """RGB euclidean distance - for when per-channel tolerance is too coarse."""
    total = 0
    for i in range(3):
        d = int(a[i]) - int(b[i])
        total += d * d
    return total ** 0.5


def wait_pixel_color(x, y, target, tolerance=10, timeout=5.0, interval=0.1):
    """Poll pixel (x, y) until it matches target within tolerance.

    Returns the matching (r, g, b) tuple, or None when the timeout expires.
    Always bounded by timeout.
    """
    deadline = time.time() + float(timeout)
    while True:
        actual = get_pixel_rgb(x, y)
        if is_color_similar(actual, target, tolerance):
            return actual
        if time.time() >= deadline:
            return None
        time.sleep(float(interval))


def wait_pixel_change(x, y, reference, tolerance=10, timeout=5.0, interval=0.1):
    """Inverse of wait_pixel_color: wait until the pixel stops matching reference.

    Returns the new (r, g, b), or None if it never changed before the timeout.
    """
    deadline = time.time() + float(timeout)
    while True:
        actual = get_pixel_rgb(x, y)
        if not is_color_similar(actual, reference, tolerance):
            return actual
        if time.time() >= deadline:
            return None
        time.sleep(float(interval))
