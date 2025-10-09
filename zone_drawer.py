"""
Редактор зон для задания «Полёт через запретные зоны»

Как запустить
-------------
python zone_drawer.py
(нужен Python 3.10+; tkinter обычно уже установлен.
Linux: sudo apt install -y python3-tk)

Что умеет
---------
• Ставить точки старта (красная) и финиша (синяя).
• Рисовать прямоугольные запретные зоны «по трём кликам»:
  1) первая вершина,
  2) вторая вершина (задаёт направление стороны),
  3) смещение перпендикуляром — прямоугольник достроится автоматически.
• Редактировать зоны перетаскиванием вершин; прямоугольность сохраняется.
• Удалять зону правым кликом внутри неё.
• Сохранять/загружать файл zones.txt в требуемом формате.

Управление
----------
• Переключатель режимов сверху: «Зона» / «Старт» / «Финиш».
• Привязка угла при выборе 2-й точки: удерживайте Shift,
  направляющая фиксируется к ближайшему из углов 0°/30°/45°/60°/90°.
• Правый клик по зоне — удалить её.
• Кнопки: «Сохранить в TXT» (сохранение), «Загрузить из TXT» (загрузка).

Файл zones.txt (совместим с симулятором)
----------------------------------------
x_start y_start
x_finish y_finish
N
x1_1 y1_1 x2_1 y2_1 x3_1 y3_1 x4_1 y4_1
...
x1_N y1_N x2_N y2_N x3_N y3_N x4_N y4_N

Примечания
----------
• Координаты в интерфейсе автоматически масштабируются под холст;
  при сохранении/загрузке используется тот же формат, что и в задании.
• Старт/финиш задаются по центру площадок. Финиш — квадрат 4x4 м.
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import math

class ZoneDrawerApp:
    def __init__(self, master):
        self.master = master
        master.title("Редактор зон для задания ")

        screen_w = master.winfo_screenwidth()
        screen_h = master.winfo_screenheight()

        mode_frame = tk.Frame(master)
        mode_frame.pack(pady=5)
        self.mode = tk.StringVar(value="zone")
        for m, label in [("zone", "Зона"), ("start", "Старт"), ("finish", "Финиш")]:
            tk.Radiobutton(mode_frame, text=label, variable=self.mode, value=m).pack(side=tk.LEFT, padx=5)

        self.canvas = None
        self.canvas_frame = tk.Frame(master)
        self.canvas_frame.pack()
        self.coord_label = tk.Label(master, text="")
        self.coord_label.pack()

        btn_frame = tk.Frame(master)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Сохранить в TXT", command=self.save_to_txt).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="Загрузить из TXT", command=self.load_from_txt).pack(side=tk.LEFT, padx=10)

        self.bounds = None
        self.start_px = None
        self.finish_px = None
        self.zones_px = []
        self.zone_ids = []
        self._current_pts = []
        self._preview_items = []
        self.handle_radius = 5
        self.handle_ids = []
        self.handle_map = {}
        self.dragging_handle = None
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.shift_down = False

        self.set_bounds()

        self.master.update_idletasks()
        req_w = self.master.winfo_reqwidth()
        req_h = self.master.winfo_reqheight()
        self.master.geometry(f"{req_w + 50}x{req_h}")

    @staticmethod
    def _clamp(v, a, b):
        return max(a, min(b, v))

    @staticmethod
    def _point_in_poly(pt, poly):
        x, y = pt
        inside = False
        n = len(poly)
        px1, py1 = poly[0]
        for i in range(1, n+1):
            px2, py2 = poly[i % n]
            if ((py1 > y) != (py2 > y)):
                xin = (px2 - px1) * (y - py1) / (py2 - py1 + 1e-12) + px1
                if x <= xin:
                    inside = not inside
            px1, py1 = px2, py2
        return inside

    @staticmethod
    def _sub(a, b):
        return (a[0]-b[0], a[1]-b[1])

    @staticmethod
    def _add(a, b):
        return (a[0]+b[0], a[1]+b[1])

    @staticmethod
    def _dot(a, b):
        return a[0]*b[0] + a[1]*b[1]

    @staticmethod
    def _mul(a, k):
        return (a[0]*k, a[1]*k)

    @staticmethod
    def _len2(v):
        return v[0]*v[0] + v[1]*v[1]

    @staticmethod
    def _perp_component(w, v):
        lv2 = ZoneDrawerApp._len2(v)
        if lv2 == 0:
            return (0.0, 0.0)
        proj_k = ZoneDrawerApp._dot(w, v) / lv2
        proj = ZoneDrawerApp._mul(v, proj_k)
        return ZoneDrawerApp._sub(w, proj)

    def _rect_from_three_points(self, p1, p2, p3):
        v = self._sub(p2, p1)
        w = self._sub(p3, p2)
        u = self._perp_component(w, v)
        A = p1
        B = p2
        C = self._add(B, u)
        D = self._add(A, u)
        return [A, B, C, D]

    def _orthogonalize_after_drag(self, rect, vi_new):
        A, B, C, D = rect
        pts = [A, B, C, D]

        left_idx = (vi_new - 1) % 4
        right_idx = (vi_new + 1) % 4
        opp_idx = (vi_new + 2) % 4

        P = pts[vi_new]
        O = pts[opp_idx]

        R_old = pts[right_idx]
        L_old = pts[left_idx]
        v0 = self._sub(R_old, pts[vi_new])
        w0 = self._sub(L_old, pts[vi_new])

        def _norm(v):
            return math.hypot(v[0], v[1])

        if _norm(v0) < 1e-9:
            e1 = (1.0, 0.0)
        else:
            e1 = (v0[0]/_norm(v0), v0[1]/_norm(v0))

        w_perp = self._perp_component(w0, v0)
        if _norm(w_perp) < 1e-9:
            e2 = (-e1[1], e1[0])
        else:
            e2 = (w_perp[0]/_norm(w_perp), w_perp[1]/_norm(w_perp))

        OP = self._sub(O, P)
        a = self._dot(OP, e1)
        b = self._dot(OP, e2)

        R_new = self._add(P, self._mul(e1, a))
        L_new = self._add(P, self._mul(e2, b))

        pts_new = [None]*4
        pts_new[vi_new]   = P
        pts_new[right_idx]= R_new
        pts_new[opp_idx]  = O
        pts_new[left_idx] = L_new
        return pts_new


    def _snap_second_point(self, p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        r = math.hypot(dx, dy)
        if r == 0:
            return p2
        ux = dx / r
        uy = dy / r
        sx = 1 if dx >= 0 else -1
        sy = 1 if dy >= 0 else -1
        inv2 = 1.0 / math.sqrt(2.0)
        sqrt3_2 = math.sqrt(3.0) / 2.0
        cands = [
            (sx * 1.0,      sy * 0.0),      # 0°
            (sx * sqrt3_2,  sy * 0.5),      # 30°
            (sx * inv2,     sy * inv2),     # 45°
            (sx * 0.5,      sy * sqrt3_2),  # 60°
            (sx * 0.0,      sy * 1.0),      # 90°
        ]
        best = max(cands, key=lambda u: abs(u[0]*ux + u[1]*uy))
        return (p1[0] + best[0]*r, p1[1] + best[1]*r)

    def to_real(self, px, py):
        y = self.y_max - px / self.canvas_w * (self.y_max - self.y_min)
        x = self.x_max - py / self.canvas_h * (self.x_max - self.x_min)
        return (x, y)

    def to_canvas(self, x, y):
        px = (self.y_max - y) / (self.y_max - self.y_min) * self.canvas_w
        py = (self.x_max - x) / (self.x_max - self.x_min) * self.canvas_h
        return int(round(px)), int(round(py))

    def set_bounds(self):
        try:
            self.x_min, self.x_max = -1200, 3700
            self.y_min, self.y_max = -1500, 1500
        except ValueError:
            messagebox.showerror("Ошибка", "Введите числовые границы.")
            return

        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            messagebox.showerror("Ошибка", "Максимум должен быть больше минимума.")
            return

        self.bounds = (self.x_min, self.y_min, self.x_max, self.y_max)

        real_w = self.y_max - self.y_min
        real_h = self.x_max - self.x_min
        aspect_ratio = real_w / real_h

        max_canvas_h = int(self.screen_h * 0.6)
        self.canvas_h = max_canvas_h
        self.canvas_w = max(200, int(self.canvas_h * aspect_ratio))

        for w in self.canvas_frame.winfo_children():
            w.destroy()

        self.canvas = tk.Canvas(self.canvas_frame, width=self.canvas_w, height=self.canvas_h, bg="white")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.redraw_all()

    def redraw_all(self):
        self.canvas.delete("all")
        self.zone_ids.clear()
        for poly in self.zones_px:
            pid = self.canvas.create_polygon(poly, outline="red", fill="", width=2)
            self.zone_ids.append(pid)
        if self.start_px:
            x, y = self.start_px
            self.start_marker = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill='red')
        if self.finish_px:
            x, y = self.finish_px
            self.finish_marker = self.canvas.create_oval(x-5, y-5, x+5, y+5, fill='blue')
        self.rebuild_handles()

    def rebuild_handles(self):
        for row in self.handle_ids:
            for hid in row:
                self.canvas.delete(hid)
        self.handle_ids = []
        self.handle_map.clear()
        r = self.handle_radius
        for zi, poly in enumerate(self.zones_px):
            row = []
            for vi, (x, y) in enumerate(poly):
                hid = self.canvas.create_oval(x-r, y-r, x+r, y+r, fill="#ffaaaa", outline="#cc0000")
                self.handle_map[hid] = (zi, vi)
                row.append(hid)
            self.handle_ids.append(row)

    def on_drag(self, event):
        if not self.dragging_handle:
            return
        zi, vi = self.dragging_handle
        px = self._clamp(event.x, 0, self.canvas_w)
        py = self._clamp(event.y, 0, self.canvas_h)
        self.zones_px[zi][vi] = (px, py)
        self.zones_px[zi] = self._orthogonalize_after_drag(self.zones_px[zi], vi)
        flat = []
        for (x, y) in self.zones_px[zi]:
            flat.extend([x, y])
        self.canvas.coords(self.zone_ids[zi], *flat)
        r = self.handle_radius
        for vj, (vx, vy) in enumerate(self.zones_px[zi]):
            hid = self.handle_ids[zi][vj]
            self.canvas.coords(hid, vx-r, vy-r, vx+r, vy+r)

    def on_release(self, event):
        if self.dragging_handle:
            self.dragging_handle = None

    def on_click(self, event):
        handle = self.canvas.find_withtag('current')
        if handle:
            hid = handle[0]
            if hid in self.handle_map:
                self.dragging_handle = self.handle_map[hid]
                return
        mode = self.mode.get()
        if mode == "zone":
            if len(self._current_pts) >= 3:
                return
            pt = (event.x, event.y)
            if len(self._current_pts) == 1 and (event.state & 0x0001):
                pt = self._snap_second_point(self._current_pts[0], pt)
            self._current_pts.append(pt)
            self.draw_preview()
            if len(self._current_pts) == 3:
                rect = self._rect_from_three_points(*self._current_pts)
                pid = self.canvas.create_polygon(rect, outline="red", fill="", width=2)
                self.zones_px.append(rect)
                self.zone_ids.append(pid)
                self._current_pts.clear()
                self.clear_preview()
                self.rebuild_handles()
        elif mode == "start":
            if self.start_px:
                self.canvas.delete(self.start_marker)
            self.start_px = (event.x, event.y)
            self.start_marker = self.canvas.create_oval(event.x-5, event.y-5, event.x+5, event.y+5, fill='red')
        elif mode == "finish":
            if self.finish_px:
                self.canvas.delete(self.finish_marker)
            self.finish_px = (event.x, event.y)
            self.finish_marker = self.canvas.create_oval(event.x-5, event.y-5, event.x+5, event.y+5, fill='blue')

    def on_motion(self, event):
        self.shift_down = bool(event.state & 0x0001)
        if self.mode.get() == "zone" and self._current_pts:
            cursor = (event.x, event.y)
            if len(self._current_pts) == 1 and self.shift_down:
                cursor = self._snap_second_point(self._current_pts[0], cursor)
            self.draw_preview(cursor=cursor)
        if self.bounds:
            x, y = self.to_real(event.x, event.y)
            self.coord_label.config(text=f"Курсор: x={x*0.01:.2f}  y={y*0.01:.2f}")

    def draw_preview(self, cursor=None):
        self.clear_preview()
        if not self._current_pts:
            return
        for x, y in self._current_pts:
            self._preview_items.append(self.canvas.create_oval(x-2, y-2, x+2, y+2, fill='black'))
        if len(self._current_pts) >= 2:
            x1, y1 = self._current_pts[0]
            x2, y2 = self._current_pts[1]
            self._preview_items.append(self.canvas.create_line(x1, y1, x2, y2, fill='black', dash=(3,)))
        if cursor:
            last = self._current_pts[-1]
            if len(self._current_pts) == 2:
                rect = self._rect_from_three_points(self._current_pts[0], self._current_pts[1], cursor)
                flat = []
                for (x, y) in rect + [rect[0]]:
                    flat.extend([x, y])
                self._preview_items.append(self.canvas.create_line(*flat, fill='gray', dash=(4,2)))
            else:
                self._preview_items.append(self.canvas.create_line(last[0], last[1], cursor[0], cursor[1], fill='gray', dash=(2,2)))

    def clear_preview(self):
        for it in self._preview_items:
            self.canvas.delete(it)
        self._preview_items.clear()

    def on_right_click(self, event):
        for i, poly in enumerate(self.zones_px):
            if self._point_in_poly((event.x, event.y), poly):
                self.canvas.delete(self.zone_ids[i])
                for hid in self.handle_ids[i]:
                    self.canvas.delete(hid)
                del self.zones_px[i]
                del self.zone_ids[i]
                del self.handle_ids[i]
                self.handle_map.clear()
                for zi, row in enumerate(self.handle_ids):
                    for vi, hid in enumerate(row):
                        self.handle_map[hid] = (zi, vi)
                break

    def clear_canvas(self):
        self.canvas.delete("all")
        self.zones_px.clear()
        self.zone_ids.clear()
        self._current_pts.clear()
        self.start_px = None
        self.finish_px = None
        self.handle_map.clear()
        self.handle_ids = []
        self.set_bounds()

    def save_to_txt(self):
        if not self.bounds:
            messagebox.showerror("Ошибка", "Сначала задайте границы.")
            return
        if not self.start_px or not self.finish_px:
            messagebox.showerror("Ошибка", "Отметьте старт и финиш.")
            return
        sx, sy = self.to_real(*self.start_px)
        fx, fy = self.to_real(*self.finish_px)
        sx_s = sx * 0.01
        sy_s = sy * 0.01
        fx_s = fx * 0.01
        fy_s = fy * 0.01
        lines = [
            f"{sx_s:.2f} {sy_s:.2f}",
            f"{fx_s:.2f} {fy_s:.2f}",
            str(len(self.zones_px))
        ]
        for poly in self.zones_px:
            pts_real = [self.to_real(x, y) for x, y in poly]
            pts_scaled = [(x * 0.01, y * 0.01) for (x, y) in pts_real]
            line = " ".join(f"{x:.2f} {y:.2f}" for x, y in pts_scaled)
            lines.append(line)
        path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text files','*.txt')])
        if path:
            with open(path, 'w') as f:
                f.write("\n".join(lines))
            messagebox.showinfo("Сохранено", f"Координаты сохранены в {path}")

    def load_from_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path:
            return
        try:
            with open(path, 'r') as f:
                lines = [line.strip() for line in f if line.strip()]
            if len(lines) < 3:
                raise ValueError("Неверный формат файла")
            sx_s, sy_s = map(float, lines[0].split())
            fx_s, fy_s = map(float, lines[1].split())
            sx = sx_s / 0.01
            sy = sy_s / 0.01
            fx = fx_s / 0.01
            fy = fy_s / 0.01
            n = int(lines[2])
            zone_lines = lines[3:3+n]
            if len(zone_lines) != n:
                raise ValueError("Несовпадение количества зон")
            self.clear_canvas()
            self.start_px = self.to_canvas(sx, sy)
            self.start_marker = self.canvas.create_oval(self.start_px[0]-5, self.start_px[1]-5, self.start_px[0]+5, self.start_px[1]+5, fill='red')
            self.finish_px = self.to_canvas(fx, fy)
            self.finish_marker = self.canvas.create_oval(self.finish_px[0]-5, self.finish_px[1]-5, self.finish_px[0]+5, self.finish_px[1]+5, fill='blue')
            for line in zone_lines:
                coords_s = list(map(float, line.split()))
                if len(coords_s) != 8:
                    raise ValueError("Каждая зона должна содержать 4 точки (8 чисел)")
                coords_real = [c / 0.01 for c in coords_s]
                pts = [(coords_real[i], coords_real[i+1]) for i in range(0, 8, 2)]
                poly_px = [self.to_canvas(x, y) for (x, y) in pts]
                pid = self.canvas.create_polygon(poly_px, outline="red", fill="", width=2)
                self.zones_px.append(poly_px)
                self.zone_ids.append(pid)
            self.rebuild_handles()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить: {e}")

if __name__ == '__main__':
    root = tk.Tk()
    app = ZoneDrawerApp(root)
    root.mainloop()
