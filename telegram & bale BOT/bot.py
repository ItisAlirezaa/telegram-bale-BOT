 
import io
import os
import time
import zlib
 
import requests
from PIL import Image, ImageOps
 
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
 
TOKEN = os.environ.get("BALE_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"
FIT_A4 = False
MAX_PDF_MB = 18
MAX_IMAGES = 200
pending = {}   
notify = {}    
 
 

 
def call(method, **params):
    r = requests.post(f"{API}/{method}", data=params, timeout=60)
    r.raise_for_status()
    return r.json()
 
 
def send_text(chat_id, text):
    try:
        call("sendMessage", chat_id=chat_id, text=text)
    except requests.RequestException as e:
        print("خطا در ارسال پیام:", e)
 
 
def send_pdf(chat_id, pdf_bytes, filename):
    r = requests.post(
        f"{API}/sendDocument",
        data={"chat_id": chat_id},
        files={"document": (filename, pdf_bytes, "application/pdf")},
        timeout=300,
    )
    r.raise_for_status()
 
 
def download_file(file_id):
    info = call("getFile", file_id=file_id)["result"]
    r = requests.get(f"{FILE_API}/{info['file_path']}", timeout=300)
    r.raise_for_status()
    return r.content
 
 

 
DPI = 150 
A4 = (595.28, 841.89)
ROTATE_BY_EXIF = {1: 0, 3: 180, 6: 90, 8: 270}
 
 
def _icc_for(img, n):
    prof = img.info.get("icc_profile")
    sig = b"GRAY" if n == 1 else b"RGB "
    if prof and len(prof) > 128 and prof[16:20] == sig:
        return prof
    return None
 
 
def prepare_jpeg(data):
    """JPEG را بدون تغییر آماده می‌کند. اگر نشد None برمی‌گرداند."""
    img = Image.open(io.BytesIO(data))
    if img.format not in ("JPEG", "MPO") or img.mode not in ("RGB", "L"):
        return None
    orientation = img.getexif().get(0x0112, 1)
    if orientation not in ROTATE_BY_EXIF:
        return None
    n = 1 if img.mode == "L" else 3
    return {
        "w": img.size[0], "h": img.size[1],
        "cs": "DeviceGray" if n == 1 else "DeviceRGB",
        "filter": "DCTDecode", "data": data,
        "rot": ROTATE_BY_EXIF[orientation],
        "icc": _icc_for(img, n), "n": n,
    }
 
 
def prepare_raw(data):
    """هر فرمت دیگری (PNG, WEBP, ...) را بدون افت کیفیت آماده می‌کند."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
 
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:  # PDF شفافیت را نمی‌پذیرد؛ پس‌زمینه سفید می‌گذاریم
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        img = bg
    elif img.mode not in ("RGB", "L"):
        img = img.convert("L" if img.mode in ("1", "I;16") else "RGB")
 
    n = 1 if img.mode == "L" else 3
    return {
        "w": img.size[0], "h": img.size[1],
        "cs": "DeviceGray" if n == 1 else "DeviceRGB",
        "filter": "FlateDecode", "data": zlib.compress(img.tobytes(), 6),
        "rot": 0, "icc": None, "n": n,
    }
 
 
def prepare_image(data):
    if data[:3] == b"\xff\xd8\xff":
        try:
            item = prepare_jpeg(data)
            if item:
                return item
        except Exception:
            pass
    return prepare_raw(data)
 
 
def _stream(dict_text, data):
    return (b"<< " + dict_text.encode() + b" /Length %d >>\nstream\n" % len(data)
            + data + b"\nendstream")
 
 
def build_pdf(items):
    objs = []
 
    def add(body):
        objs.append(body)
        return len(objs)
 
    add(b"")  
    add(b"")  
    page_ids = []
    icc_cache = {}
 
    for it in items:
        w, h, rot = it["w"], it["h"], it["rot"]
 
        cs = "/" + it["cs"]
        if it["icc"]:
            key = (it["icc"], it["n"])
            if key not in icc_cache:
                icc_cache[key] = add(_stream(
                    f"/N {it['n']} /Alternate /{it['cs']} /Filter /FlateDecode",
                    zlib.compress(it["icc"])))
            cs = f"[/ICCBased {icc_cache[key]} 0 R]"
 
        img_id = add(_stream(
            f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
            f"/ColorSpace {cs} /BitsPerComponent 8 /Filter /{it['filter']}",
            it["data"]))
 
        swapped = rot in (90, 270)
        dw, dh = (h, w) if swapped else (w, h)   
        if FIT_A4:
            pw, ph = (A4[1], A4[0]) if dw > dh else A4
            mw, mh = (ph, pw) if swapped else (pw, ph)
            margin = 20
            scale = min((mw - 2 * margin) / w, (mh - 2 * margin) / h)
        else:
            scale = 72.0 / DPI
            mw, mh = w * scale, h * scale
        iw, ih = w * scale, h * scale
        x, y = (mw - iw) / 2, (mh - ih) / 2
 
        content = f"q {iw:.3f} 0 0 {ih:.3f} {x:.3f} {y:.3f} cm /Im0 Do Q".encode()
        c_id = add(_stream("", content))
        page_ids.append(add(
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {mw:.3f} {mh:.3f}] "
             f"/Rotate {rot} /Resources << /XObject << /Im0 {img_id} 0 R >> >> "
             f"/Contents {c_id} 0 R >>").encode()))
 
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{p} 0 R" for p in page_ids)
    objs[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
 
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(body)
        out.write(b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write((f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
               f"startxref\n{xref}\n%%EOF\n").encode())
    return out.getvalue()
 
 
def split_by_size(items, limit_bytes):
    chunks, cur, size = [], [], 0
    for it in items:
        n = len(it["data"])
        if cur and size + n > limit_bytes:
            chunks.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        chunks.append(cur)
    return chunks
 
 
def send_all_as_pdf(chat_id, raw_images):
    prepared = []
    for i, data in enumerate(raw_images, 1):
        try:
            prepared.append(prepare_image(data))
        except Exception as e:
            print(f"عکس {i} قابل خواندن نبود:", e)
            send_text(chat_id, f"عکس شماره {i} قابل خواندن نبود و رد شد.")
 
    if not prepared:
        send_text(chat_id, "عکس قابل استفاده‌ای پیدا نشد.")
        return
 
    chunks = split_by_size(prepared, MAX_PDF_MB * 1024 * 1024)
    send_text(chat_id, f"در حال ساخت PDF از {len(prepared)} عکس ...")
    for n, chunk in enumerate(chunks, 1):
        pdf = build_pdf(chunk)
        name = "photos.pdf" if len(chunks) == 1 else f"photos_part{n}.pdf"
        send_pdf(chat_id, pdf, name)
 
 

 
def get_image_file_id(message):
    if message.get("photo"):
        return message["photo"][-1]["file_id"]
    doc = message.get("document")
    if doc and str(doc.get("mime_type", "")).startswith("image/"):
        return doc["file_id"]
    return None
 
 
def handle_message(message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
 
    if text.startswith("/start"):
        send_text(
            chat_id,
            "سلام! 👋\n"
            "عکس‌هایت را یکی‌یکی (یا همه با هم) بفرست.\n"
            "وقتی تمام شد دستور /pdf را بزن تا همه را در یک PDF بگذارم.\n"
            "برای بهترین کیفیت، عکس‌ها را «به صورت فایل» بفرست.\n"
            "برای پاک کردن عکس‌ها: /cancel",
        )
        return
 
    if text.startswith("/pdf"):
        images = pending.pop(chat_id, [])
        notify.pop(chat_id, None)
        if not images:
            send_text(chat_id, "هنوز عکسی نفرستاده‌ای.")
            return
        try:
            send_all_as_pdf(chat_id, images)
        except Exception as e:
            print("خطا:", e)
            send_text(chat_id, "مشکلی در ساخت یا ارسال PDF پیش آمد.")
        return
 
    if text.startswith("/cancel"):
        pending.pop(chat_id, None)
        notify.pop(chat_id, None)
        send_text(chat_id, "همه‌ی عکس‌ها پاک شدند.")
        return
 
    file_id = get_image_file_id(message)
    if not file_id:
        send_text(chat_id, "لطفاً عکس بفرست. وقتی تمام شد /pdf بزن.")
        return
 
    if len(pending.get(chat_id, [])) >= MAX_IMAGES:
        send_text(chat_id, f"حداکثر {MAX_IMAGES} عکس مجاز است. /pdf بزن.")
        return
 
    try:
        data = download_file(file_id)
        pending.setdefault(chat_id, []).append(data)
        notify[chat_id] = time.time()
    except Exception as e:
        print("خطا در دانلود عکس:", e)
        send_text(chat_id, "این عکس دانلود نشد، دوباره بفرستش.")
 
 
def flush_notifications():
    """۲ ثانیه بعد از آخرین عکس، یک پیام با تعداد کل عکس‌ها می‌فرستد."""
    now = time.time()
    for chat_id, t in list(notify.items()):
        if now - t >= 2:
            del notify[chat_id]
            n = len(pending.get(chat_id, []))
            send_text(chat_id, f"✅ {n} عکس ذخیره شد. عکس بعدی را بفرست یا /pdf بزن.")
 
def main():
    print("ربات روشن شد ...")
    offset = None
    while True:
        try:
            params = {"timeout": 2 if notify else 30}
            if offset is not None:
                params["offset"] = offset
            updates = call("getUpdates", **params).get("result", [])
            for upd in updates:
                offset = upd["update_id"] + 1
                if "message" in upd:
                    handle_message(upd["message"])
            flush_notifications()
        except requests.RequestException as e:
            print("خطای شبکه:", e)
            time.sleep(5)
 
 
if __name__ == "__main__":
    main()