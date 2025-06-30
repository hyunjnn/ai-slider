import io
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Callable, List, Tuple

import google.generativeai as genai
from models.task import File, SlideSettings
from services.slides.prompts_service import PromptsService


class SlideService:
    
    
    def __init__(self):
        """Initialize the Gemini model and prompt service
        """
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-1.5-flash", 
            generation_config = {
                "max_output_tokens": 4096
            }
        )
        self.prompt_service = PromptsService()
        

    async def generate_slides(
        self,
        theme: str,
        files: list[File],
        settings: SlideSettings,
        status_update_fn: Callable[[str], None],
    ) -> Tuple[bytes, bytes]:
        """Generate slides from uploaded files and user-defined settings
        """
        await status_update_fn("Analyzing your uploaded files...")
        # await asyncio.sleep(5)
        gemini_files = []
        for file in files:
            file_reader = io.BytesIO(file.data)
            gemini_file = genai.upload_file(file_reader, display_name=file.filename, mime_type=file.type)
            gemini_files.append(gemini_file)

        await status_update_fn("Designing your presentation...")

        prompt = self.prompt_service.generate_prompt(theme, settings)
        logging.info("Prompts: ", prompt)

        await status_update_fn("Preparing the slide content...")

        parts = [{"file_data": {"uri": f.uri}} for f in gemini_files]
        parts.append({"text": prompt})
        
        contents = [{"role": "user", "parts": parts}]
        
        token_info = self.model.count_tokens(contents=contents)
        if token_info.total_tokens > 16384:
            raise ValueError("Documents are too large to process")
       
        response = self.model.generate_content(contents=contents)
        response_text = response.candidates[0].content.parts[0].text
        
        marp_text = self.extract_markdown_content(response_text)
        if not marp_text:
            raise ValueError("Failed to generate presentation.")

        await status_update_fn("Finalizing your slides...")

        return self.render_with_marp(marp_text, theme)


    def render_with_marp(self, markdown: str, theme: str) -> Tuple[bytes, bytes]:
        """Render the markdown content into PDF and HTML using Marp CLI
        """
        temp_dir = tempfile.mkdtemp(prefix="ai-slider-")
        try:
            md_path = os.path.join(temp_dir, "ppt.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(markdown)

            pdf_path = os.path.join(temp_dir, "ppt.pdf")
            html_path = os.path.join(temp_dir, "ppt.html")

            theme_path = os.path.join("services", "slides", "themes", f"{theme}.css")
            theme_arg = ["--theme", theme_path] if os.path.exists(theme_path) else ["--theme", theme]

            self.run_marp_cli(md_path, pdf_path, ["--pdf"] + theme_arg)
            self.run_marp_cli(md_path, html_path, ["--html"] + theme_arg)

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            with open(html_path, "rb") as f:
                html_bytes = f.read()

            return pdf_bytes, html_bytes
        finally:
            shutil.rmtree(temp_dir)


    def run_marp_cli(self, input_path: str, output_path: str, extra_args: List[str]):
        """Execute the Marp CLI command to convert markdown into slides
        """
        cmd = ["npx", "@marp-team/marp-cli", input_path, "--output", output_path] + extra_args
        logging.info("Running Marp CLI: %s", ' '.join(cmd))
        result = subprocess.run(cmd, capture_output=True)
        
        print("stdout: %s", result.stdout.decode())
        print("stderr: %s", result.stderr.decode())
        logging.info("stdout: %s", result.stdout.decode())
        
        if result.returncode != 0:
            logging.error("Marp CLI error: %s", result.stderr.decode())
            raise RuntimeError("Failed to render presentation with Marp")


    def extract_markdown_content(self, text: str) -> str:
        """Extract markdown content from the Gemini model's response
        """
        lines = text.splitlines()
        start, end = -1, -1
        for i, line in enumerate(lines):
            if line.startswith("```"):
                if start == -1:
                    start = i
                else:
                    end = i
                    break
        return "\n".join(lines[start + 1:end]) if start != -1 and end != -1 else text
