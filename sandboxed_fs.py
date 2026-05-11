"""
Sandboxed Virtual File System for CodeUp

Provides safe file operations within a confined workspace directory.
All file operations are restricted to /workspace folder.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Optional, Dict, List


class SandboxedFileSystem:
    """Manages file operations within a sandboxed workspace."""
    
    def __init__(self, workspace_dir: Optional[str] = None):
        """
        Initialize sandboxed filesystem.
        
        Args:
            workspace_dir: Path to workspace root. If None, uses temp directory.
        """
        if workspace_dir is None:
            # Create a temp directory for the workspace
            self.workspace_dir = tempfile.mkdtemp(prefix="codeup_workspace_")
        else:
            self.workspace_dir = workspace_dir
            os.makedirs(self.workspace_dir, exist_ok=True)
        
        # Ensure workspace path is absolute and normalized
        self.workspace_dir = os.path.abspath(self.workspace_dir)
    
    def _validate_path(self, filepath: str) -> str:
        """
        Validate and normalize path to ensure it's within workspace.
        Resolves symlinks on both sides to prevent symlink-escape attacks.

        Args:
            filepath: Path to validate

        Returns:
            Absolute normalized path within workspace

        Raises:
            ValueError: If path attempts to escape workspace (including via symlink)
        """
        candidate = Path(self.workspace_dir) / filepath
        # Resolve symlinks. strict=False so non-existent paths (writes) still resolve.
        resolved = candidate.resolve(strict=False)
        workspace_resolved = Path(self.workspace_dir).resolve(strict=False)
        try:
            resolved.relative_to(workspace_resolved)
        except ValueError:
            raise ValueError(f"Path '{filepath}' is outside workspace")
        return str(resolved)
    
    # Configurable via SANDBOX_MAX_FILE_SIZE env var. Default 5 MB.
    MAX_FILE_SIZE = int(os.environ.get("SANDBOX_MAX_FILE_SIZE", "5000000"))

    def write(self, filepath: str, content: str, encoding: str = "utf-8") -> Dict:
        """
        Write file to workspace.
        
        Args:
            filepath: Path relative to workspace
            content: File content
            encoding: Text encoding (default: utf-8)
            
        Returns:
            {"success": bool, "path": str, "size": int, "error": str}
        """
        try:
            # enforce size limit before writing to avoid resource exhaustion
            if len(content.encode(encoding)) > self.MAX_FILE_SIZE:
                raise ValueError(f"File exceeds maximum size of {self.MAX_FILE_SIZE} bytes")

            abs_path = self._validate_path(filepath)
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            
            # Write file
            with open(abs_path, "w", encoding=encoding) as f:
                f.write(content)
            
            size = len(content.encode(encoding))
            return {
                "success": True,
                "path": filepath,
                "size": size,
            }
        except Exception as e:
            return {
                "success": False,
                "path": filepath,
                "error": str(e)
            }
    
    def read(self, filepath: str, encoding: str = "utf-8") -> Dict:
        """
        Read file from workspace.
        
        Args:
            filepath: Path relative to workspace
            encoding: Text encoding (default: utf-8)
            
        Returns:
            {"success": bool, "content": str, "size": int, "error": str}
        """
        try:
            abs_path = self._validate_path(filepath)
            
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "path": filepath,
                    "error": "File not found"
                }
            
            if not os.path.isfile(abs_path):
                return {
                    "success": False,
                    "path": filepath,
                    "error": "Path is not a file"
                }
            
            with open(abs_path, "r", encoding=encoding) as f:
                content = f.read()
            
            return {
                "success": True,
                "path": filepath,
                "content": content,
                "size": len(content)
            }
        except Exception as e:
            return {
                "success": False,
                "path": filepath,
                "error": str(e)
            }
    
    def delete(self, filepath: str) -> Dict:
        """
        Delete file from workspace.
        
        Args:
            filepath: Path relative to workspace
            
        Returns:
            {"success": bool, "path": str, "error": str}
        """
        try:
            abs_path = self._validate_path(filepath)
            
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "path": filepath,
                    "error": "File not found"
                }
            
            if os.path.isfile(abs_path):
                os.remove(abs_path)
            else:
                return {
                    "success": False,
                    "path": filepath,
                    "error": "Path is not a file"
                }
            
            return {
                "success": True,
                "path": filepath
            }
        except Exception as e:
            return {
                "success": False,
                "path": filepath,
                "error": str(e)
            }
    
    def list_files(self, dirpath: str = ".") -> Dict:
        """
        List files in workspace directory.
        
        Args:
            dirpath: Directory path relative to workspace
            
        Returns:
            {"success": bool, "files": list, "dirs": list, "error": str}
        """
        try:
            abs_path = self._validate_path(dirpath)
            
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": "Directory not found",
                    "files": [],
                    "dirs": []
                }
            
            if not os.path.isdir(abs_path):
                return {
                    "success": False,
                    "error": "Path is not a directory",
                    "files": [],
                    "dirs": []
                }
            
            files = []
            dirs = []
            
            for entry in os.listdir(abs_path):
                entry_path = os.path.join(abs_path, entry)
                if os.path.isfile(entry_path):
                    files.append({
                        "name": entry,
                        "size": os.path.getsize(entry_path)
                    })
                elif os.path.isdir(entry_path):
                    dirs.append(entry)
            
            return {
                "success": True,
                "files": sorted(files, key=lambda x: x["name"]),
                "dirs": sorted(dirs)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "files": [],
                "dirs": []
            }
    
    def get_workspace_info(self) -> Dict:
        """Get information about the workspace."""
        try:
            total_files = 0
            total_size = 0
            
            for root, dirs, files in os.walk(self.workspace_dir):
                total_files += len(files)
                for file in files:
                    total_size += os.path.getsize(os.path.join(root, file))
            
            return {
                "success": True,
                "workspace": self.workspace_dir,
                "total_files": total_files,
                "total_size": total_size,
                "available": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def cleanup(self):
        """Remove the entire workspace directory (use with caution)."""
        try:
            if os.path.exists(self.workspace_dir):
                import shutil
                shutil.rmtree(self.workspace_dir)
                return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": True}


# Per-session sandbox storage (thread-safe dict keyed by session id)
import threading
_sandboxes: dict = {}
_sandboxes_lock = threading.Lock()

import atexit

@atexit.register
def _cleanup_all_sandboxes_on_exit():
    with _sandboxes_lock:
        for sb in list(_sandboxes.values()):
            try:
                sb.cleanup()
            except Exception:
                pass
        _sandboxes.clear()

def get_sandbox(session_id: str = "default") -> "SandboxedFileSystem":
    """
    Get or create a sandbox for a specific session.
    Each session gets its own isolated temp directory.
    Pass session_id from Flask's get_session_id() so users
    never share each other's workspace.
    """
    with _sandboxes_lock:
        if session_id not in _sandboxes:
            _sandboxes[session_id] = SandboxedFileSystem()
        return _sandboxes[session_id]