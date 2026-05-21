"""Pronunciation dictionary for AI news narration system."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class PronunciationEntry:
    """A pronunciation entry for the TTS dictionary."""
    original: str
    spoken_as: str
    replace_in_tts_script: bool
    reason: str


class PronunciationDictionary:
    """Pronunciation dictionary for AI news terms."""

    # Comprehensive pronunciation guide for AI/tech terms
    PRONUNCIATIONS = [
        # Model names
        PronunciationEntry("GPT-4o", "gee pee tee four oh", True, "Model name - read character by character"),
        PronunciationEntry("GPT-5.5", "gee pee tee five point five", True, "Model name - read version as spoken words"),
        PronunciationEntry("GPT-5", "gee pee tee five", True, "Model name"),
        PronunciationEntry("GPT-4", "gee pee tee four", True, "Model name"),
        PronunciationEntry("GPT-3.5", "gee pee tee three point five", True, "Model name"),
        PronunciationEntry("Claude", "clawd", True, "Anthropic model - rhymes with 'proud'"),
        PronunciationEntry("Claude 3", "clawd three", True, "Model name"),
        PronunciationEntry("Claude 3.5", "clawd three point five", True, "Model name"),
        PronunciationEntry("Gemini 2.5 Pro", "Gemini two point five pro", True, "Google model - version as words"),
        PronunciationEntry("Gemini 2.0", "Gemini two point zero", True, "Google model"),
        PronunciationEntry("Gemini", "Gemini", False, "Google model - proper noun"),
        PronunciationEntry("Llama", "lah-muh", True, "Meta model - soft pronunciation"),
        PronunciationEntry("Llama 3", "lah-muh three", True, "Model name"),
        PronunciationEntry("Llama 3.1", "lah-muh three point one", True, "Model name"),
        PronunciationEntry("Llama 3.2", "lah-muh three point two", True, "Model name"),
        PronunciationEntry("Llama 4", "lah-muh four", True, "Model name"),
        PronunciationEntry("Mistral", "miss-TRAHL", True, "AI company - French pronunciation"),
        PronunciationEntry("Mixtral", "mix-TRAHL", True, "Mistral model - mix and TRAHHL"),
        PronunciationEntry("Qwen", "kwen", True, "Alibaba model - rhymes with 'when'"),
        PronunciationEntry("Qwen2.5", "kwen two point five", True, "Model name"),
        PronunciationEntry("Qwen3", "kwen three", True, "Model name"),
        PronunciationEntry("DeepSeek", "deep-seek", False, "AI company - readable as English"),
        PronunciationEntry("DeepSeek R1", "deep-seek aitch one", True, "Model name"),
        PronunciationEntry("o1", "oh one", True, "OpenAI model - read as 'oh one'"),
        PronunciationEntry("o3", "oh three", True, "OpenAI model"),
        PronunciationEntry("o4", "oh four", True, "OpenAI model"),
        PronunciationEntry("Sora", "sora", False, "OpenAI video model - proper noun"),
        PronunciationEntry("Veo", "vay-oh", True, "Google video model"),
        PronunciationEntry("Imagen", "im-ah-jen", True, "Google image model"),
        PronunciationEntry("DALL-E", "doll ee", True, "OpenAI image model - Italian pronunciation"),
        PronunciationEntry("DALL-E 3", "doll ee three", True, "Model name"),
        PronunciationEntry("Midjourney", "mid-jur-nee", False, "AI art - readable as English"),
        PronunciationEntry("Stable Diffusion", "stable diff-yoo-zhen", False, "AI model - readable"),
        PronunciationEntry("Flux", "fluhks", False, "AI model - readable as English"),
        
        # Company names
        PronunciationEntry("Anthropic", "anthro-pik", True, "AI company - not 'anthrop-ic'"),
        PronunciationEntry("OpenAI", "open eye", True, "Company name - read AI as letters"),
        PronunciationEntry("Nvidia", "en-VID-ee-uh", True, "Tech company - emphasis on VID"),
        PronunciationEntry("NVIDIA", "en-VID-ee-uh", True, "Tech company - all caps variant"),
        PronunciationEntry("Meta", "MEE-tuh", False, "Company - readable as English"),
        PronunciationEntry("Google", "GOO-gul", False, "Company - readable as English"),
        PronunciationEntry("Microsoft", "mi-kro-sof", False, "Company - readable as English"),
        PronunciationEntry("Amazon", "am-uh-zon", False, "Company - readable as English"),
        PronunciationEntry("Apple", "AP-ul", False, "Company - readable as English"),
        PronunciationEntry("Tesla", "TEL-suh", False, "Company - readable as English"),
        PronunciationEntry("xAI", "ex A I", True, "Elon Musk's AI company - read as letters"),
        PronunciationEntry("xAI", "ex A I", True, "Elon Musk's AI company - lowercase variant"),
        PronunciationEntry("Alibaba", "al-ih-bah-bah", False, "Company - readable as English"),
        PronunciationEntry("ByteDance", "byte-dance", False, "Company - readable as English"),
        PronunciationEntry("Snowflake", "snow-fleek", False, "Company - readable as English"),
        PronunciationEntry("Databricks", "day-ta-briks", False, "Company - readable as English"),
        PronunciationEntry("Hugging Face", "hugging face", False, "Company - readable as English"),
        PronunciationEntry("Scale AI", "scale A I", True, "Company name"),
        PronunciationEntry("Cohere", "co-HAIR-ee", True, "AI company - emphasis on HAIR"),
        PronunciationEntry("Perplexity", "per-plek-si-ty", False, "AI company - readable as English"),
        PronunciationEntry("Character AI", "Character A I", True, "Company name"),
        PronunciationEntry("Runway", "run-way", False, "AI video company - readable"),
        PronunciationEntry("Replicate", "rep-li-kate", False, "AI platform - readable as English"),
        PronunciationEntry("Gradio", "grah-dee-oh", True, "AI interface library"),
        PronunciationEntry("LangChain", "lang chain", False, "Framework - readable as English"),
        PronunciationEntry("LlamaIndex", "lama in-dex", True, "Framework - lama not llama"),
        PronunciationEntry("Meridian Labs", "mer-ih-dee-an labs", True, "Nonprofit - emphasis on dee-an"),
        PronunciationEntry("Altara", "al-TAR-uh", True, "AI startup - emphasis on TAR"),
        
        # Acronyms
        PronunciationEntry("API", "A P I", True, "Acronym - read each letter"),
        PronunciationEntry("AI", "A I", True, "Acronym - read as letters"),
        PronunciationEntry("GPU", "G P U", True, "Acronym - read each letter"),
        PronunciationEntry("CPU", "C P U", True, "Acronym - read each letter"),
        PronunciationEntry("LPU", "L P U", True, "Acronym - read each letter"),
        PronunciationEntry("ML", "em el", True, "Machine Learning - read as letters"),
        PronunciationEntry("DL", "dee el", True, "Deep Learning - read as letters"),
        PronunciationEntry("NLP", "en el pee", True, "Natural Language Processing - read as letters"),
        PronunciationEntry("LLM", "el el em", True, "Large Language Model - read as letters"),
        PronunciationEntry("SaaS", "say-s", True, "Software as a Service - read as letters"),
        PronunciationEntry("B2B", "bee to bee", True, "Business to Business - read as letters"),
        PronunciationEntry("B2C", "bee to see", True, "Business to Consumer - read as letters"),
        PronunciationEntry("URL", "you ar el", True, "Acronym - read as letters"),
        PronunciationEntry("HTTPS", "aych tee tee pes", True, "Protocol - read as letters"),
        PronunciationEntry("JSON", "jay sun", True, "Format - read as 'jay sun'"),
        PronunciationEntry("REST", "rest", False, "Architecture - reads correctly as word"),
        PronunciationEntry("OS", "oh es", True, "Operating System - read as letters"),
        PronunciationEntry("UI", "yoo eye", True, "User Interface - read as letters"),
        PronunciationEntry("UX", "you ex", True, "User Experience - read as letters"),
        PronunciationEntry("FAQ", "fack", True, "Frequently Asked Questions - reads as 'fack'"),
        PronunciationEntry("ROI", "ar oh eye", True, "Return on Investment - read as letters"),
        PronunciationEntry("KPI", "kay pee eye", True, "Key Performance Indicator - read as letters"),
        PronunciationEntry("IoT", "eye oh tee", True, "Internet of Things - read as letters"),
        PronunciationEntry("VR", "vee ar", True, "Virtual Reality - read as letters"),
        PronunciationEntry("AR", "ay ar", True, "Augmented Reality - read as letters"),
        PronunciationEntry("ML", "em el", True, "Machine Learning - read as letters"),
        PronunciationEntry("CV", "see vee", True, "Computer Vision or Curriculum Vitae - read as letters"),
        PronunciationEntry("NLP", "en el pee", True, "Natural Language Processing - read as letters"),
        
        # Technical terms
        PronunciationEntry("transformer", "trans-form-er", False, "AI architecture - readable as English"),
        PronunciationEntry("neural", "noo-ral", False, "Technical term - readable as English"),
        PronunciationEntry("algorithm", "al-go-rith-em", False, "Technical term - readable"),
        PronunciationEntry("parameter", "pa-ram-e-ter", False, "Technical term - readable"),
        PronunciationEntry("parameters", "pa-ram-e-terz", False, "Technical term - readable"),
        PronunciationEntry("dataset", "dayt-set", False, "Technical term - readable as English"),
        PronunciationEntry("training", "train-ing", False, "Technical term - readable as English"),
        PronunciationEntry("inference", "in-fer-ence", False, "Technical term - readable as English"),
        PronunciationEntry("deployment", "dee-ploy-ment", False, "Technical term - readable"),
        PronunciationEntry("infrastructure", "in-fo-struh-ktcher", False, "Technical term - readable"),
        PronunciationEntry("bandwidth", "band-width", False, "Technical term - readable as English"),
        PronunciationEntry("latency", "lay-ten-see", True, "Technical term - emphasis on TEN"),
        PronunciationEntry("throughput", "throo-put", False, "Technical term - readable as English"),
        PronunciationEntry("scalability", "skay-luh-bil-i-ty", False, "Technical term - readable"),
        PronunciationEntry("optimization", "op-ti-mi-ZAY-shun", False, "Technical term - readable"),
        PronunciationEntry("regularization", "reg-yu-la-RAY-zay-shun", False, "Technical term - readable"),
        PronunciationEntry("backpropagation", "bak-pro-puh-GAY-shun", True, "Technical term - emphasis on GAY"),
        PronunciationEntry("softmax", "soft-max", False, "Technical term - readable as English"),
        PronunciationEntry("activation", "ak-ti-VAY-shun", False, "Technical term - readable"),
        PronunciationEntry("convolution", "kon-vo-LOO-shun", False, "Technical term - readable"),
        PronunciationEntry("recurrent", "ree-kuh-rent", False, "Technical term - readable"),
        PronunciationEntry("bidirectional", "bye-di-RECK-shuh-nal", True, "Technical term - emphasis on RECK"),
        PronunciationEntry("attention", "uh-TEN-shun", False, "Technical term - emphasis on TEN"),
        PronunciationEntry("embedding", "em-BED-ing", False, "Technical term - emphasis on BED"),
        PronunciationEntry("tokenizer", "token-izer", False, "Technical term - readable as English"),
        PronunciationEntry("token", "token", False, "Technical term - readable as English"),
        PronunciationEntry("context window", "con-text win-doh", False, "Technical term - readable as English"),
        PronunciationEntry("fine-tuning", "fine-tyoo-ning", False, "Technical term - readable as English"),
        PronunciationEntry("supervised", "soo-pur-vized", False, "Technical term - readable"),
        PronunciationEntry("unsupervised", "un-su-pur-vized", False, "Technical term - readable"),
        PronunciationEntry("reinforcement", "ree-in-for-suh-ment", False, "Technical term - readable"),
        PronunciationEntry("gradient", "GRAY-dee-ent", False, "Technical term - emphasis on GRADE"),
        PronunciationEntry("optimizer", "op-ti-my-zur", False, "Technical term - readable"),
        PronunciationEntry("hyperparameter", "hy-per-uh-PA-ram-e-ter", True, "Technical term - emphasis on PA"),
        PronunciationEntry("overfitting", "oh-ver-fit-ing", False, "Technical term - readable as English"),
        PronunciationEntry("generalization", "jen-er-al-ih-ZAY-shun", False, "Technical term - readable"),
        PronunciationEntry("batch", "batch", False, "Technical term - readable as English"),
        PronunciationEntry("epoch", "EPOK", True, "Technical term - rhymes with 'mock'"),
        PronunciationEntry("loss", "loss", False, "Technical term - readable as English"),
        PronunciationEntry("accuracy", "ak-yuh-rah-see", False, "Technical term - readable"),
        PronunciationEntry("precision", "pre-ZIH-zhun", False, "Technical term - readable"),
        PronunciationEntry("recall", "ri-sawl", False, "Technical term - readable as English"),
        PronunciationEntry("F1 score", "ef-one score", True, "Metric - read as 'ef-one'"),
        PronunciationEntry("confusion matrix", "con-fyoo-zhun ma-trix", False, "Technical term - readable"),
        PronunciationEntry("ROC curve", "ar oh curve", True, "Metric - read as letters"),
        PronunciationEntry("AUC", "ay you see", True, "Metric - read as letters"),
        
        # Version numbers and dates
        PronunciationEntry("2026", "two thousand twenty-six", True, "Year - read as full words"),
        PronunciationEntry("2025", "two thousand twenty-five", True, "Year - read as full words"),
        PronunciationEntry("2024", "two thousand twenty-four", True, "Year - read as full words"),
        PronunciationEntry("2023", "two thousand twenty-three", True, "Year - read as full words"),
        PronunciationEntry("GTC 2026", "gee tee see two thousand twenty-six", True, "Conference + year"),
        PronunciationEntry("GTC 2025", "gee tee see two thousand twenty-five", True, "Conference + year"),
        PronunciationEntry("Q1", "cue one", True, "Quarter - read as 'cue one'"),
        PronunciationEntry("Q2", "cue two", True, "Quarter - read as 'cue two'"),
        PronunciationEntry("Q3", "cue three", True, "Quarter - read as 'cue three'"),
        PronunciationEntry("Q4", "cue four", True, "Quarter - read as 'cue four'"),
        PronunciationEntry("Q1 2026", "cue one two thousand twenty-six", True, "Quarter and year"),
        
        # Product names
        PronunciationEntry("Jensen Huang", "JEN-sun HWONG", True, "NVIDIA CEO - HWONG rhymes with 'long'"),
        PronunciationEntry("Sam Altman", "sam ALTMAN", True, "OpenAI CEO - ALTMAN rhymes with 'hometown'"),
        PronunciationEntry("Dario Amodei", "dah-ree-oh ah-moh-DAY-ee", True, "Anthropic CEO - Italian name"),
        PronunciationEntry("Demis Hassabis", "DAY-mis HAS-uh-biss", True, "Google DeepMind CEO"),
        PronunciationEntry("Ilya Sutskever", "il-ya soots-KAY-vehr", True, "OpenAI Co-founder - Russian name"),
        PronunciationEntry("Mistral AI", "miss-TRAHL A I", True, "Company name"),
        PronunciationEntry("Cohere AI", "co-HAIR-ee A I", True, "Company name"),
        PronunciationEntry("Character AI", "Character A I", True, "Company name"),
        PronunciationEntry("Perplexity AI", "per-plek-si-ty A I", True, "Company name"),
        PronunciationEntry("Hugging Face", "hugging face", False, "Company - readable as English"),
        PronunciationEntry("Replicate", "rep-li-kate", False, "Platform - readable as English"),
        PronunciationEntry("Runway ML", "run-way em el", True, "Company name"),
        PronunciationEntry("Stability AI", "stab-il-i-ty A I", True, "Company name"),
        PronunciationEntry("Midjourney", "mid-jur-nee", False, "Platform - readable as English"),
        PronunciationEntry("Leonardo", "lee-oh-NAHR-doh", False, "AI art platform - readable"),
        PronunciationEntry("ComfyUI", "com-fee yoo eye", True, "Interface - read UI as letters"),
        PronunciationEntry("Automatic1111", "automatic eleven eleven", True, "WebUI - read numbers as words"),
        PronunciationEntry("Forge", "forge", False, "WebUI variant - readable as English"),
        PronunciationEntry("Fooocus", "foo-koo-s", True, "WebUI - read as 'foo cus'"),
        
        # Other terms
        PronunciationEntry("GitHub", "github", False, "Platform - reads as one word"),
        PronunciationEntry("GitLab", "git-lab", False, "Platform - reads as two words"),
        PronunciationEntry("Docker", "DOCK-er", False, "Platform - readable as English"),
        PronunciationEntry("Kubernetes", "kyoo-ber-neh-teez", True, "Orchestration - emphasis on KOO"),
        PronunciationEntry("K8s", "kay eight es", True, "Abbreviation - read as letters"),
        PronunciationEntry("Linux", "LINUX", True, "OS - emphasized pronunciation"),
        PronunciationEntry("Ubuntu", "uh-BOON-too", True, "Linux distro - emphasis on BOON"),
        PronunciationEntry("Debian", "DEE-bee-an", True, "Linux distro - emphasis on DEE"),
        PronunciationEntry("Raspberry Pi", "raz-berry pie", False, "Hardware - readable as English"),
        PronunciationEntry("Jetson", "JET-sun", False, "NVIDIA platform - readable as English"),
        PronunciationEntry("H100", "aitch one zero zero", True, "GPU model - read each character"),
        PronunciationEntry("H200", "aitch two zero zero", True, "GPU model"),
        PronunciationEntry("B200", "bee two zero zero", True, "GPU model"),
        PronunciationEntry("GB200", "gee bee two zero zero", True, "GPU model"),
        PronunciationEntry("A100", "ay one zero zero", True, "GPU model - read as letters"),
        PronunciationEntry("H800", "aitch eight zero zero", True, "GPU model - China variant"),
        PronunciationEntry("L40S", "el four oh es", True, "GPU model - read as letters"),
        PronunciationEntry("RTX", "ar tee eks", True, "GPU brand - read as letters"),
        PronunciationEntry("Tensor Core", "TEN-sor core", False, "NVIDIA tech - readable as English"),
        PronunciationEntry("CUDA", "kyoo dah", True, "NVIDIA platform - read as 'kyoo dah'"),
        PronunciationEntry("ROCm", "rohk em", True, "AMD platform - read as 'rohk em'"),
        PronunciationEntry("HIP", "hip", False, "AMD platform - reads as word"),
        PronunciationEntry("vCPU", "vee see pee yoo", True, "Virtual CPU - read as letters"),
        PronunciationEntry("RAM", "are ay em", True, "Memory - read as letters"),
        PronunciationEntry("SSD", "ess ess dee", True, "Storage - read as letters"),
        PronunciationEntry("NVMe", "en vee em eee", True, "Storage protocol - read as letters"),
        PronunciationEntry("PCIe", "pee eye see eee", True, "Bus standard - read as letters"),
        PronunciationEntry("DDR5", "dee dee ar five", True, "Memory type - read as letters"),
        PronunciationEntry("LPDDR5", "el pee dee dee ar five", True, "Mobile memory - read as letters"),
        PronunciationEntry("TB", "tee bee", True, "Terabyte - read as letters"),
        PronunciationEntry("GB", "gee bee", True, "Gigabyte - read as letters"),
        PronunciationEntry("MB", "em bee", True, "Megabyte - read as letters"),
        PronunciationEntry("KB", "kay bee", True, "Kilobyte - read as letters"),
        PronunciationEntry("MHz", "em eh chee", True, "Frequency - read as letters"),
        PronunciationEntry("GHz", "jay gee chee", True, "Frequency - read as letters"),
        PronunciationEntry("Watt", "wot", False, "Power - readable as English"),
        PronunciationEntry("TFLOPS", "tee-eff-lips", True, "Performance - read as 'tee-eff-lips'"),
        PronunciationEntry("FLOPS", "flops", False, "Operations - readable as English"),
        PronunciationEntry("PSU", "pee ess yoo", True, "Power Supply - read as letters"),
        PronunciationEntry("FPS", "eff pee ess", True, "Frames per second - read as letters"),
        PronunciationEntry("Hz", "aych zee", True, "Hertz - read as letters"),
        PronunciationEntry("bit", "bit", False, "Data unit - readable as English"),
        PronunciationEntry("byte", "bite", False, "Data unit - reads as 'bite'"),
        PronunciationEntry("kilobyte", "kil-oh-byte", False, "Data unit - readable"),
        PronunciationEntry("megabyte", "meg-oh-byte", False, "Data unit - readable"),
        PronunciationEntry("gigabyte", "gig-oh-byte", False, "Data unit - readable"),
        PronunciationEntry("terabyte", "ter-oh-byte", False, "Data unit - readable"),
        PronunciationEntry("petabyte", "pet-oh-byte", False, "Data unit - readable"),
        PronunciationEntry("exabyte", "ex-oh-byte", False, "Data unit - readable"),
    ]
    
    # Build lookup tables
    _original_to_spoken = {entry.original.lower(): entry.spoken_as for entry in PRONUNCIATIONS}
    _original_to_entry = {entry.original.lower(): entry for entry in PRONUNCIATIONS}
    
    def get_pronunciation(self, term: str) -> Optional[PronunciationEntry]:
        """Get pronunciation entry for a term."""
        return self._original_to_entry.get(term.lower())
    
    def get_spoken_form(self, term: str) -> Optional[str]:
        """Get spoken form for a term."""
        entry = self.get_pronunciation(term)
        return entry.spoken_as if entry else None
    
    def should_replace(self, term: str) -> bool:
        """Check if a term should be replaced in TTS script."""
        entry = self.get_pronunciation(term)
        return entry.replace_in_tts_script if entry else False
    
    def substitute_pronunciations(self, text: str) -> str:
        """Substitute pronunciations in text for safer TTS reading."""
        result = text
        
        # Sort by length (longest first) to avoid partial matches
        sorted_terms = sorted(self._original_to_spoken.keys(), key=len, reverse=True)
        
        for term in sorted_terms:
            spoken = self._original_to_spoken[term]
            entry = self._original_to_entry[term]
            
            if not entry.replace_in_tts_script:
                continue
            
            # Use word boundary matching
            pattern = r'\b' + re.escape(term) + r'\b'
            result = re.sub(pattern, spoken, result, flags=re.IGNORECASE)
        
        return result
    
    def find_pronunciation_issues(self, text: str) -> list[str]:
        """Find terms in text that may be mispronounced by TTS."""
        issues = []
        text_lower = text.lower()
        
        for term in self._original_to_entry.keys():
            if term in text_lower:
                entry = self._original_to_entry[term]
                issues.append({
                    "term": term,
                    "spoken_as": entry.spoken_as,
                    "reason": entry.reason,
                })
        
        return issues
