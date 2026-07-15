"""Quality Gate Stage for the Council of Cats.

This stage runs Mittens' script review before render to catch:
- Malformed text (e.g., "expand its. Partnership")
- Grammar errors
- Source verification
- Channel correctness
"""

import subprocess
from pathlib import Path
from typing import Optional

from src.config import Channel
from src.stages.script import ScriptStage
from src.utils import get_job_dir, load_json, save_json


class QualityGateError(Exception):
    """Quality gate rejection."""
    pass


class QualityGateStage:
    """Quality gate stage that runs Mittens' script reviewer."""
    
    def __init__(self, job_id: str, channel: Channel = Channel.STOIC_MODERNIZED):
        self.job_id = job_id
        self.channel = channel
        self.job_dir = get_job_dir(job_id)
        self.script_path = self.job_dir / "script" / "script.json"
        self.quality_report_path = self.job_dir / "quality_gate.json"
        
    def run(self) -> dict:
        """Run the quality gate.
        
        Returns:
            dict with approval status
            
        Raises:
            QualityGateError if script is rejected
        """
        if not self.script_path.exists():
            raise QualityGateError(f"Script not found: {self.script_path}")
        
        # Load script
        script_data = load_json(self.script_path)
        title = script_data.get("title", "Untitled")
        
        # Run Mittens' script reviewer via subprocess
        reviewer_script = Path.home() / ".hermes" / "scripts" / "content-pipeline" / "mittens_script_reviewer.py"
        
        if not reviewer_script.exists():
            raise QualityGateError(f"Mittens reviewer not found: {reviewer_script}")
        
        project_root = Path(__file__).resolve().parents[2]
        cmd = ["python3", str(reviewer_script), self.job_id, self.channel.value, str(project_root)]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # Parse output as JSON
        import json
        output = result.stdout.strip()
        
        # Find JSON in output
        try:
            # Try to find JSON in stdout
            if output.startswith("{"):
                quality_result = json.loads(output)
            else:
                # Look for JSON in stderr or full output
                full_output = result.stdout + result.stderr
                start = full_output.find("{")
                end = full_output.rfind("}") + 1
                if start >= 0 and end > start:
                    quality_result = json.loads(full_output[start:end])
                else:
                    raise QualityGateError(f"Could not parse quality gate result: {result.stdout[:200]}")
        except json.JSONDecodeError as e:
            raise QualityGateError(f"Failed to parse quality gate output: {e}. Output: {result.stdout[:500]}")
        
        # Save quality report
        save_json(quality_result, self.quality_report_path)
        
        # Check approval status
        if quality_result.get("status") == "rejected":
            issues = quality_result.get("issues", [])
            issue_text = "\n".join([f"  - {issue['type']}: {issue.get('fix', 'Unknown')}" for issue in issues])
            error_msg = f"Quality gate rejected:\n{issue_text}\n\nRecommended action: {quality_result.get('recommended_action', 'Fix issues and resubmit')}"
            raise QualityGateError(error_msg)
        
        # Approved
        return {
            "status": "approved",
            "job_id": self.job_id,
            "title": title,
            "channel": self.channel.value,
            "issues": quality_result.get("issues", []),
            "approved_at": quality_result.get("approved_at"),
            "report_path": str(self.quality_report_path)
        }
