"""Inverse of capture/src/convert.cpp, including its even-pixel letterbox."""
def stream_size(display, quality, fps):
    from carplay_proto.displaysettings import display_modes
    modes = display_modes(display)
    if quality != 3:
        return modes[quality]
    budget = 1280 * 720 if fps > 30 else 1920 * 1080
    return next((mode for mode in modes if mode[0] * mode[1] <= budget), modes[-1])


class Viewport:
    def __init__(self, width, height, native_width, native_height, rotation=0):
        if rotation not in (0, 90, 180, 270):
            raise ValueError('rotation must be 0, 90, 180 or 270')
        if min(width, height, native_width, native_height) < 2:
            raise ValueError('invalid screen geometry')
        self.width, self.height = width, height
        self.nw, self.nh, self.rotation = native_width, native_height, rotation
        self.cw, self.ch = ((native_height, native_width) if rotation in (90, 270)
                            else (native_width, native_height))
        bw, bh = width, width * self.ch // self.cw
        if bh > height:
            bh, bw = height, height * self.cw // self.ch
        self.bw, self.bh = bw & ~1, bh & ~1
        if not self.bw or not self.bh:
            raise ValueError('screen aspect ratio is too extreme')
        self.bx = ((width - self.bw) // 2) & ~1
        self.by = ((height - self.bh) // 2) & ~1

    def map(self, x, y, clamp=False):
        x, y = x - self.bx, y - self.by
        if not clamp and not (0 <= x < self.bw and 0 <= y < self.bh):
            return None
        # Include both native edges so system swipe gestures reach pixel zero.
        rx = max(0, min(self.bw - 1, x)) * (self.cw - 1) // (self.bw - 1)
        ry = max(0, min(self.bh - 1, y)) * (self.ch - 1) // (self.bh - 1)
        if self.rotation == 90:
            return ry, self.nh - 1 - rx
        if self.rotation == 270:
            return self.nw - 1 - ry, rx
        if self.rotation == 180:
            return self.nw - 1 - rx, self.nh - 1 - ry
        return rx, ry
