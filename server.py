import os
import uuid
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pathlib import Path
import shutil
from fastapi.middleware.cors import CORSMiddleware
from core.exception_handler import APIException
from core.models import API_Resolution
from core.messages import *
from contextlib import asynccontextmanager
# from prometheus_client import make_asgi_app
from prometheus_fastapi_instrumentator import Instrumentator

from lib import (
    BASE_STORAGE,
    get_path,
    get_cache_path,
    create_thumbnail,
    init_storage,
)

app = FastAPI(
    openapi_url="/fs/openapi.json",  # Move OpenAPI to `/api/openapi.json`
    docs_url="/fs/docs",  # Keep Swagger UI at `/docs`
    redoc_url="/fs/redoc"  # Keep ReDoc at `/redoc`
)

# app.mount("/metrics", make_asgi_app())
Instrumentator().instrument(app).expose(app)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_storage()
    yield


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # If it's a known APIException
    if isinstance(exc, APIException):
        resolution = API_Resolution(
            status=exc.status,
            error_code=exc.code,
            message=str(exc.details),
        )
        return JSONResponse(
            status_code=exc.status,
            content=resolution.dict(),
        )
    status_code = HTTP_500_INTERNAL_SERVER_ERROR
    # If it's an unexpected internal error
    resolution = API_Resolution(
        status=status_code,
        error_code=INTERNAL_SERVER_ERROR,
        message=str(exc),
    )
    return JSONResponse(
        status_code=status_code,
        content=resolution.dict(),
    )



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this for security in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.put("/fs/upload/{entity_type}/{owner_id}/{entity_id}/")
async def upload_file(entity_type: str, owner_id: str, entity_id: str, file: UploadFile = File(...)):
    """
    Uploads a file and stores it in the designated folder.
    """
    entity_path = get_path(entity_type, owner_id, entity_id)
    entity_path.mkdir(parents=True, exist_ok=True)

    file_path = entity_path / f"{uuid.uuid4()}.{file.filename.split('.')[-1]}"

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"✅ File saved: {file_path}")
    except Exception as e:
        raise APIException(status=500,code= HTTP_410_GONE,details=f"File upload failed: {str(e)}")
    access_path = str(file_path).replace("/fs/data","/fs/files")
    return {"filename": file.filename, "path": access_path}

@app.get("/fs/{entity_type}/{owner_id}/{entity_id}/{filename}")
async def get_file(entity_type: str, owner_id: str, entity_id: str, filename: str, detailed: bool = False):
    """
    Retrieve a file from the server.
    - If 'detailed' is True, return the original file.
    - If False, return a thumbnail (or generate one if missing).
    """

    # Construct file paths
    entity_path = get_path(entity_type, owner_id, entity_id)
    file_path = entity_path / filename
  
    print(f"🔍 Checking file: {file_path}")

    # Check if the original file exists
    if not file_path.exists() or not file_path.is_file():
        raise APIException(status=404,code= HTTP_404_NOT_FOUND,details="File not found")

    # If detailed is requested, return the original file
    if detailed:
        print(f"📂 Returning original file: {file_path}")
        return FileResponse(file_path, filename=filename)

    # Thumbnail processing
    cache_path = get_cache_path(entity_type, owner_id, entity_id) / filename

    if not cache_path.exists():
        print(f"⚠️ Thumbnail not found, generating one for {file_path}")
        try:
            create_thumbnail(file_path, cache_path)
        except Exception as e:
            print(f"Thumbnail error: {e}")

        # If thumbnail creation failed, return original file as fallback
        if not cache_path.exists():
            print(f"❌ Thumbnail generation failed, returning original file")
            return FileResponse(file_path, filename=filename)

    print(f"📸 Returning thumbnail: {cache_path}")
    return FileResponse(cache_path, filename=f"thumbnail_{filename}")

@app.delete("/fs/files/{entity_type}/{owner_id}/{entity_id}/{filename}")
async def delete_file(entity_type: str, owner_id: str, entity_id: str, filename: str):
    """
    Deletes a specific file.
    """
    file_path = get_path(entity_type, owner_id, entity_id) / filename

    if not file_path.exists():
        raise APIException(status=404,code= HTTP_404_NOT_FOUND,details="File not found")

    try:
        file_path.unlink()
        return {"message": f"File '{filename}' deleted successfully"}
    except Exception as e:
        raise APIException(status=500,code= HTTP_417_EXPECTATION_FAILED,details=f"Error deleting file: {str(e)}")

@app.get("/fs/files/{entity_type}/{owner_id}/")
async def list_user_files(entity_type: str, owner_id: str):
    user_path = BASE_STORAGE / entity_type / owner_id

    if not user_path.exists():
        raise APIException(
            status=404,
            code=HTTP_404_NOT_FOUND,
            details="User directory not found",
        )

    files = {
        entity.name: [f.name for f in entity.iterdir() if f.is_file()]
        for entity in user_path.iterdir()
        if entity.is_dir()
    }

    return {"user_id": owner_id, "files": files}


@app.get("/fs/stream/{entity_type}/{owner_id}/{entity_id}/{filename}")
async def stream_file(
    entity_type: str, 
    owner_id: str, 
    entity_id: str, 
    filename: str,
    request: Request,
    detailed: bool = False
):
    """
    Stream a file to the client. Can be displayed directly in the browser
    (images, videos, PDFs, audio, etc.) or streamed for large files.
    """
    
    # Construct file path
    entity_path = get_path(entity_type, owner_id, entity_id)
    file_path = entity_path / filename
    
    # Check if the file exists
    if not file_path.exists() or not file_path.is_file():
        raise APIException(
            status=404,
            code=HTTP_404_NOT_FOUND,
            details="File not found"
        )
    
    # Determine content type based on file extension
    content_type = _get_content_type(filename)
    
    # Get file size for range requests (partial content)
    file_size = os.path.getsize(file_path)
    
    # Handle range requests (for video/audio streaming)
    range_header = request.headers.get("range")
    
    if range_header:
        try:
            # Parse range header (bytes=start-end)
            start, end = _parse_range_header(range_header, file_size)
            
            # If end is not specified, use entire file
            if end is None:
                end = file_size - 1
            
            # Validate range
            if start < 0 or end >= file_size or start > end:
                raise APIException(
                    status=416,
                    code="RANGE_NOT_SATISFIABLE",
                    details="Invalid range request"
                )
            
            # Calculate content length for the chunk
            content_length = end - start + 1
            
            # Create a generator for streaming the chunk
            def chunk_generator():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    bytes_to_read = content_length
                    chunk_size = 8192  # 8KB chunks
                    while bytes_to_read > 0:
                        chunk = f.read(min(chunk_size, bytes_to_read))
                        if not chunk:
                            break
                        bytes_to_read -= len(chunk)
                        yield chunk
            
            # Return partial content response
            return StreamingResponse(
                chunk_generator(),
                status_code=206,  # Partial Content
                media_type=content_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                    "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                }
            )
        except (ValueError, IndexError):
            # Invalid range header - send entire file
            pass
    
    # For non-range requests, stream the entire file
    def file_generator():
        with open(file_path, "rb") as f:
            chunk_size = 8192
            while chunk := f.read(chunk_size):
                yield chunk
    
    # Determine if it should be displayed inline or downloaded
    # For common browser-viewable formats, use inline; otherwise, attachment
    viewable_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', 
                          '.pdf', '.mp4', '.webm', '.ogg', '.mp3', '.wav',
                          '.txt', '.html', '.css', '.js', '.json', '.xml'}
    
    _, ext = os.path.splitext(filename)
    disposition = "inline" if ext.lower() in viewable_extensions else "attachment"
    
    return StreamingResponse(
        file_generator(),
        media_type=content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename=\"{filename}\"",
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",  # Cache for 1 day
        }
    )

def _get_content_type(filename: str) -> str:
    """Get content type based on file extension."""
    extension = os.path.splitext(filename)[1].lower()
    
    content_types = {
        # Images
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.svg': 'image/svg+xml',
        '.bmp': 'image/bmp',
        '.ico': 'image/x-icon',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        
        # Videos
        '.mp4': 'video/mp4',
        '.mpeg': 'video/mpeg',
        '.webm': 'video/webm',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.wmv': 'video/x-ms-wmv',
        '.flv': 'video/x-flv',
        '.mkv': 'video/x-matroska',
        '.3gp': 'video/3gpp',
        
        # Audio
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        '.aac': 'audio/aac',
        '.flac': 'audio/flac',
        '.wma': 'audio/x-ms-wma',
        
        # Documents
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.txt': 'text/plain',
        '.rtf': 'application/rtf',
        '.csv': 'text/csv',
        
        # Code
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.yaml': 'text/yaml',
        '.yml': 'text/yaml',
        '.md': 'text/markdown',
        
        # Archives
        '.zip': 'application/zip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
        '.tar': 'application/x-tar',
        '.gz': 'application/gzip',
        
        # Fonts
        '.ttf': 'font/ttf',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.eot': 'application/vnd.ms-fontobject',
        
        # Others
        '.bin': 'application/octet-stream',
    }
    
    return content_types.get(extension, 'application/octet-stream')

def _parse_range_header(range_header: str, file_size: int) -> tuple:
    """Parse HTTP Range header (bytes=start-end)."""
    # Remove "bytes=" prefix
    range_value = range_header.replace("bytes=", "")
    
    # Split into start and end
    parts = range_value.split("-")
    
    start = int(parts[0]) if parts[0] else 0
    end = int(parts[1]) if len(parts) > 1 and parts[1] else None
    
    # If start is not specified, it's a suffix range (bytes=-last_n_bytes)
    if start == 0 and parts[0] == '':
        start = file_size - end
        end = file_size - 1
    
    return start, end