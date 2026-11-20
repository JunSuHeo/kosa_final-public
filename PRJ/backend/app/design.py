"""Bounded, static design hints. Never imports or executes repository code."""
import re
from .schema import DesignProfile


def extract_design(analysis):
    profile = DesignProfile().model_dump()
    evidence = []
    colors = {}
    for path, content in sorted(analysis["files"].items()):
        if not path.lower().endswith((".css", ".scss", ".less", ".tsx", ".jsx", ".vue", ".html")):
            continue
        found = False
        for key, pattern in {
            "primary": r"(?:--[\w-]*(?:primary|brand)[\w-]*|(?:background|background-color))\s*:\s*(#[0-9a-fA-F]{6})\b",
            "background": r"(?:--[\w-]*background[\w-]*|background-color)\s*:\s*(#[0-9a-fA-F]{6})\b",
            "surface": r"--[\w-]*(?:surface|card)[\w-]*\s*:\s*(#[0-9a-fA-F]{6})\b",
            "text": r"(?:--[\w-]*(?:foreground|text)[\w-]*|(?<!-)color)\s*:\s*(#[0-9a-fA-F]{6})\b",
        }.items():
            match = re.search(pattern, content, re.I)
            if match and key not in colors:
                colors[key] = match[1]
                found = True
        match = re.search(r"border-radius\s*:\s*(\d+)px", content)
        if match and "radius" not in colors:
            colors["radius"] = min(24, int(match[1]))
            found = True
        match = re.search(r"(?:--[\w-]*spacing[\w-]*|gap)\s*:\s*(\d+)px", content)
        if match and "spacing" not in colors:
            colors["spacing"] = max(8, min(32, int(match[1])))
            found = True
        match = re.search(r"font-family\s*:\s*([^;}]+)", content)
        if match and "font" not in colors:
            family = match[1].lower()
            colors["font"] = "mono" if "monospace" in family else "sans" if "sans-serif" in family else "serif" if "serif" in family else "system"
            found = True
        if re.search(r"(?:class(?:Name)?=[\"'][^\"']*sidebar|\.sidebar\s*\{)", content) and "shell" not in colors:
            colors["shell"] = "sidebar"
            found = True
        if found and len(evidence) < 12:
            evidence.append(path)
    profile.update(colors)
    profile["evidence"] = evidence
    return DesignProfile.model_validate(profile).model_dump()
