import mimetypes


def validate_file_type(filename: str):
    allowed_exts = ['.pdf', '.md', '.txt']
    ext = mimetypes.guess_extension(mimetypes.guess_type(filename)[0] or "")
    if ext not in allowed_exts:
        return False
    
    return True