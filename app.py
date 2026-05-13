import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import shutil
import os
import struct
import io

from PIL import Image, ImageTk
import win32api
import win32con
import win32gui
import win32ui

ICON_SIZES = [256, 128, 64, 48, 32, 16]
PREVIEW_SIZE = 96
THUMB_SIZE = 40


def get_exe_icon_image(exe_path):
    try:
        import icoextract
        extractor = icoextract.IcoExtract(exe_path)
        ico_data = extractor.get_icon()
        img = Image.open(io.BytesIO(ico_data))
        frames = []
        try:
            while True:
                frames.append(img.copy())
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        best = max(frames, key=lambda f: f.size[0] * f.size[1]) if frames else img
        return best.convert("RGBA")
    except Exception:
        pass

    try:
        large, small = win32gui.ExtractIconEx(exe_path, 0)
        hicon = (large or small or [None])[0]
        if not hicon:
            return None
        size = 48
        screen_dc = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(screen_dc)
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc_mem = hdc.CreateCompatibleDC()
        hdc_mem.SelectObject(hbmp)
        win32gui.DrawIconEx(hdc_mem.GetSafeHdc(), 0, 0, hicon, size, size, 0, None, 0x0003)
        bmpdata = hbmp.GetBitmapBits(True)
        img = Image.frombuffer("RGBA", (size, size), bmpdata, "raw", "BGRA", 0, 1)
        for h in (large or []):
            win32gui.DestroyIcon(h)
        for h in (small or []):
            win32gui.DestroyIcon(h)
        win32gui.ReleaseDC(0, screen_dc)
        return img
    except Exception:
        return None


def image_to_ico_bytes(img_path):
    img = Image.open(img_path).convert("RGBA")
    max_dim = max(img.size)
    sizes = [(s, s) for s in ICON_SIZES if s <= max(max_dim * 2, 32)]
    if not sizes:
        sizes = [(32, 32)]
    buf = io.BytesIO()
    img.save(buf, format="ICO", sizes=sizes)
    return buf.getvalue()


def build_ico_resources(ico_bytes):
    _reserved, _type, count = struct.unpack_from("<HHH", ico_bytes, 0)
    image_list = []
    grp_entries = b""
    for i in range(count):
        off = 6 + i * 16
        width, height, color_count, res2 = struct.unpack_from("<BBBB", ico_bytes, off)
        planes, bit_count = struct.unpack_from("<HH", ico_bytes, off + 4)
        bytes_in_res, img_offset = struct.unpack_from("<II", ico_bytes, off + 8)
        icon_id = i + 1
        image_list.append((icon_id, ico_bytes[img_offset: img_offset + bytes_in_res]))
        grp_entries += struct.pack(
            "<BBBBHHIH", width, height, color_count, res2, planes, bit_count, bytes_in_res, icon_id
        )
    grp_data = struct.pack("<HHH", 0, 1, count) + grp_entries
    return grp_data, image_list


def replace_exe_icon(exe_path, ico_bytes):
    grp_data, image_list = build_ico_resources(ico_bytes)
    handle = win32api.BeginUpdateResource(exe_path, False)
    try:
        for icon_id, img_data in image_list:
            win32api.UpdateResource(handle, win32con.RT_ICON, icon_id, img_data)
        win32api.UpdateResource(handle, win32con.RT_GROUP_ICON, 1, grp_data)
        win32api.EndUpdateResource(handle, False)
    except Exception:
        win32api.EndUpdateResource(handle, True)
        raise


def make_photo(img, size):
    thumb = img.copy()
    thumb.thumbnail((size, size), Image.LANCZOS)
    bg = Image.new("RGBA", (size, size), (69, 71, 90, 255))
    offset = ((size - thumb.width) // 2, (size - thumb.height) // 2)
    bg.paste(thumb, offset, thumb)
    return ImageTk.PhotoImage(bg)


class ExeRow(tk.Frame):
    def __init__(self, parent, path, on_remove, **kw):
        super().__init__(parent, bg="#313244", **kw)
        self.path = path
        self._photo = None

        self.icon_lbl = tk.Label(self, bg="#45475a", width=THUMB_SIZE, height=THUMB_SIZE)
        self.icon_lbl.pack(side="left", padx=(8, 6), pady=6)

        info = tk.Frame(self, bg="#313244")
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=os.path.basename(path), bg="#313244", fg="#cdd6f4",
                 font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
        self.status_lbl = tk.Label(info, text="Loading icon...", bg="#313244",
                                   fg="#6c7086", font=("Segoe UI", 8), anchor="w")
        self.status_lbl.pack(fill="x")

        tk.Button(self, text="✕", command=on_remove, bg="#313244", fg="#f38ba8",
                  font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
                  activebackground="#45475a", activeforeground="#f38ba8",
                  padx=6).pack(side="right", padx=6)

        sep = tk.Frame(self, bg="#45475a", height=1)
        sep.pack(fill="x", side="bottom")

        threading.Thread(target=self._load_icon, daemon=True).start()

    def _load_icon(self):
        img = get_exe_icon_image(self.path)
        if img:
            photo = make_photo(img, THUMB_SIZE)
            self.after(0, lambda: self._apply_icon(photo))
        else:
            self.after(0, lambda: self.status_lbl.config(text="No icon found"))

    def _apply_icon(self, photo):
        self._photo = photo
        self.icon_lbl.config(image=photo)
        self.status_lbl.config(text=os.path.dirname(self.path), fg="#585b70")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Replace EXE Icon")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self.img_path = None
        self._img_photo = None
        self._exe_rows = []

        self._setup_window_icon()
        self._build_ui()

    def _setup_window_icon(self):
        import sys, tempfile
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base, "icone.png")
        if not os.path.exists(icon_path):
            return
        try:
            img = Image.open(icon_path).convert("RGBA")
            tmp = tempfile.NamedTemporaryFile(suffix=".ico", delete=False)
            img.save(tmp, format="ICO", sizes=[(256,256),(48,48),(32,32),(16,16)])
            tmp.close()
            self.wm_iconbitmap(tmp.name)
            self._tmp_icon = tmp.name
        except Exception:
            pass

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#313244", background="#89b4fa",
                        bordercolor="#1e1e2e", lightcolor="#89b4fa", darkcolor="#89b4fa")

        # Header
        header = tk.Frame(self, bg="#1e1e2e")
        header.pack(fill="x", padx=24, pady=(18, 4))
        tk.Label(header, text="Replace EXE Icon", font=("Segoe UI", 16, "bold"),
                 bg="#1e1e2e", fg="#cdd6f4").pack(side="left")
        tk.Label(header, text="v1.0", font=("Segoe UI", 9),
                 bg="#1e1e2e", fg="#585b70").pack(side="left", padx=(10, 0), pady=(6, 0))

        # Main area
        main = tk.Frame(self, bg="#1e1e2e")
        main.pack(padx=24, pady=4, fill="both")

        # Left: EXE list
        left = tk.Frame(main, bg="#1e1e2e")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        tk.Label(left, text="EXE Files", font=("Segoe UI", 10, "bold"),
                 bg="#1e1e2e", fg="#a6adc8").pack(anchor="w", pady=(0, 4))

        list_wrap = tk.Frame(left, bg="#313244")
        list_wrap.pack(fill="both", expand=True)

        canvas = tk.Canvas(list_wrap, bg="#313244", highlightthickness=0, width=320, height=260)
        scroll = ttk.Scrollbar(list_wrap, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(canvas, bg="#313244")
        self._canvas_window = canvas.create_window((0, 0), window=self._list_frame, anchor="nw")

        def on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(self._canvas_window, width=canvas.winfo_width())

        self._list_frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self._canvas_window, width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._canvas = canvas
        self._empty_lbl = tk.Label(self._list_frame, text="Nenhum .exe adicionado",
                                   bg="#313244", fg="#585b70", font=("Segoe UI", 9))
        self._empty_lbl.pack(pady=30)

        tk.Button(left, text="+ Add EXE", command=self._add_exe,
                  bg="#89b4fa", fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=12, pady=5).pack(anchor="w", pady=(8, 0))

        # Arrow
        tk.Label(main, text="→", font=("Segoe UI", 26, "bold"),
                 bg="#1e1e2e", fg="#585b70").grid(row=0, column=1, padx=10)

        # Right: new icon
        right = tk.Frame(main, bg="#313244", padx=16, pady=16)
        right.grid(row=0, column=2, sticky="nsew")

        tk.Label(right, text="New Icon", font=("Segoe UI", 10, "bold"),
                 bg="#313244", fg="#cdd6f4").pack()

        preview_wrap = tk.Frame(right, bg="#45475a", width=PREVIEW_SIZE, height=PREVIEW_SIZE)
        preview_wrap.pack(pady=10)
        preview_wrap.pack_propagate(False)

        self.new_icon_lbl = tk.Label(preview_wrap, bg="#45475a", text="?",
                                     fg="#6c7086", font=("Segoe UI", 24))
        self.new_icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

        tk.Button(right, text="Select Image", command=self._select_image,
                  bg="#a6e3a1", fg="#1e1e2e", font=("Segoe UI", 9, "bold"),
                  relief="flat", cursor="hand2", padx=10, pady=5).pack()

        self.img_name_lbl = tk.Label(right, text="Nenhuma imagem", bg="#313244",
                                     fg="#6c7086", font=("Segoe UI", 8), wraplength=140)
        self.img_name_lbl.pack(pady=(8, 0))

        # Bottom
        self.progress = ttk.Progressbar(self, style="TProgressbar",
                                        mode="determinate", length=480)
        self.progress.pack(pady=(14, 2), padx=24, fill="x")

        self.status_lbl = tk.Label(self, text="", bg="#1e1e2e", fg="#a6adc8",
                                   font=("Segoe UI", 9))
        self.status_lbl.pack()

        self.replace_btn = tk.Button(
            self, text="Replace Icons", command=self._do_replace,
            bg="#f38ba8", fg="#1e1e2e", font=("Segoe UI", 12, "bold"),
            relief="flat", cursor="hand2", padx=28, pady=9, state="disabled",
            activebackground="#eba0ac", activeforeground="#1e1e2e"
        )
        self.replace_btn.pack(pady=(10, 6))

        tk.Label(self, text="by Mazarati", font=("Segoe UI", 8),
                 bg="#1e1e2e", fg="#45475a").pack(pady=(0, 12))

    def _add_exe(self):
        paths = filedialog.askopenfilenames(
            title="Select EXE file(s)",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        for path in paths:
            if any(r.path == path for r in self._exe_rows):
                continue
            self._empty_lbl.pack_forget()
            row = ExeRow(self._list_frame, path, lambda p=path: self._remove_exe(p))
            row.pack(fill="x")
            self._exe_rows.append(row)
        self._check_ready()

    def _remove_exe(self, path):
        for row in self._exe_rows:
            if row.path == path:
                row.destroy()
                self._exe_rows.remove(row)
                break
        if not self._exe_rows:
            self._empty_lbl.pack(pady=30)
        self._check_ready()

    def _select_image(self):
        path = filedialog.askopenfilename(
            title="Select image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.webp *.ico"), ("All files", "*.*")]
        )
        if not path:
            return
        self.img_path = path
        self.img_name_lbl.config(text=os.path.basename(path), fg="#a6adc8")
        try:
            img = Image.open(path).convert("RGBA")
            photo = make_photo(img, PREVIEW_SIZE)
            self._img_photo = photo
            self.new_icon_lbl.config(image=photo, text="")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image:\n{e}")
            return
        self._check_ready()

    def _check_ready(self):
        ok = bool(self._exe_rows) and bool(self.img_path)
        self.replace_btn.config(state="normal" if ok else "disabled")

    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.replace_btn.config(state=state)

    def _do_replace(self):
        self._set_busy(True)
        self.progress["value"] = 0
        self.status_lbl.config(text="Starting...", fg="#a6adc8")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            ico_bytes = image_to_ico_bytes(self.img_path)
            exes = [r.path for r in self._exe_rows]
            total = len(exes)
            errors = []

            for i, exe in enumerate(exes):
                name = os.path.basename(exe)
                self.after(0, lambda n=name, idx=i: self.status_lbl.config(
                    text=f"[{idx+1}/{total}] Processing {n}..."))

                try:
                    base, ext = os.path.splitext(exe)
                    bkp = base + "_bkp" + ext
                    if os.path.exists(bkp):
                        os.remove(bkp)
                    os.rename(exe, bkp)
                    shutil.copy2(bkp, exe)
                    replace_exe_icon(exe, ico_bytes)
                except Exception as e:
                    errors.append(f"{name}: {e}")

                pct = int((i + 1) / total * 100)
                self.after(0, lambda p=pct: self.progress.configure(value=p))

            self.after(0, lambda: self._on_done(total, errors))
        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _on_done(self, total, errors):
        self._set_busy(False)
        if errors:
            self.status_lbl.config(text=f"Done with {len(errors)} error(s)", fg="#fab387")
            messagebox.showwarning("Partial success",
                                   f"{total - len(errors)}/{total} replaced.\n\nErrors:\n" +
                                   "\n".join(errors))
        else:
            self.status_lbl.config(text=f"Done! {total} file(s) updated.", fg="#a6e3a1")
            messagebox.showinfo("Success", f"{total} icon(s) replaced successfully!")

    def _on_error(self, msg):
        self._set_busy(False)
        self.status_lbl.config(text=f"Error: {msg}", fg="#f38ba8")
        messagebox.showerror("Error", f"Failed:\n\n{msg}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
