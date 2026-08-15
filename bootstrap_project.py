from pathlib import Path
import base64
import io
import shutil
import zipfile

root = Path(__file__).resolve().parent
b = root / ".bootstrap"
ordered = [
    b / "chunk_00.txt",
    b / "chunk_01.txt",
    b / "chunk_02.txt",
    b / "chunk_03.txt",
    b / "chunk_04.txt",
    b / "chunk_05.txt",
    b / "chunk_06.txt",
    b / "tail_a.txt",
    b / "tail_b0a.txt",
    b / "tail_b0b.txt",
    b / "tail_b0c.txt",
    b / "tail_b0d0.txt",
    b / "tail_b0d1.txt",
    b / "tail_b1.txt",
    b / "tail_b2.txt",
]

payload = "".join(p.read_text(encoding="utf-8").strip() for p in ordered)
if len(payload) != 107700:
    raise RuntimeError(f"Unexpected bootstrap payload length: {len(payload)}")

data = base64.b64decode(payload, validate=True)
with zipfile.ZipFile(io.BytesIO(data)) as archive:
    bad = archive.testzip()
    if bad is not None:
        raise RuntimeError(f"Corrupt archive member: {bad}")
    archive.extractall(root)

# Leave the repository clean after this one-time import.
shutil.rmtree(b)
workflow = root / ".github" / "workflows" / "bootstrap.yml"
if workflow.exists():
    workflow.unlink()
    try:
        workflow.parent.rmdir()
        workflow.parent.parent.rmdir()
    except OSError:
        pass
Path(__file__).unlink()
