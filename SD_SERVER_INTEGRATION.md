# SD Server Image Generation Integration

## Overview

The image generation stage now supports **two image generation methods**:

1. **SD Server** (Recommended) - Connects to a local Stable Diffusion server (Automatic1111 or ComfyUI)
2. **SD CLI** - Uses stable-diffusion.cpp CLI directly

The pipeline automatically detects and uses SD server if available, falling back to SD CLI otherwise.

## Architecture Changes

### Files Modified

1. **`src/config.py`**
   - Added `SD_SERVER = "sd_server"` to `ImageProvider` enum
   - Added SD server configuration settings:
     - `sd_server_url` - Server URL (default: `http://localhost:1234`)
     - `sd_server_api_path` - API endpoint (default: `/sdapi/v1/txt2img`)
     - `sd_server_timeout_seconds` - Request timeout (default: 300s)

2. **`src/stages/images.py`**
   - Added `SdServerImageGeneration` class for SD server-based generation
   - Updated `ImageGenerationStage.run()` to check SD server first
   - Added `_sd_server_available()` method for health checks

3. **`.env.example`**
   - Added SD server configuration section
   - Documented all SD server settings

4. **`README.md`**
   - Updated Configuration section with SD server details
   - Updated Architecture section

## Usage

### Prerequisites

You need a local Stable Diffusion server running. Options:

#### Option 1: Automatic1111 Web UI

```bash
# Install Automatic1111
git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui
cd stable-diffusion-webui

# Install requirements
./webui.sh

# Start server with API enabled
./webui.sh --api
```

#### Option 2: ComfyUI

```bash
# Install ComfyUI
git clone https://github.com/comfyanonymous/ComfyUI
cd ComfyUI

# Install requirements
pip install -r requirements.txt

# Start server
python main.py --api
```

### Configuration

Add to `.env`:

```bash
# SD Server settings (optional - uses SD CLI if not configured)
SD_SERVER_URL=http://localhost:1234
SD_SERVER_API_PATH=/sdapi/v1/txt2img
SD_SERVER_TIMEOUT_SECONDS=300
```

### Priority

The pipeline checks providers in this order:

1. **Mock mode** (if `MOCK_MODE=true`)
2. **SD Server** (if server is accessible)
3. **SD CLI** (if CLI and models are available)
4. **Error** (if neither is available)

### Running the Pipeline

```bash
# The pipeline will automatically use SD server if available
python -m src.main run "your topic here"

# Or specify individual stages
python -m src.main images --job-id <job_id>
```

## API Compatibility

The implementation uses the **Automatic1111 API format**, which is compatible with:

- ✅ Automatic1111 Web UI (`/sdapi/v1/txt2img`)
- ✅ ComfyUI (with appropriate endpoint mapping)
- ✅ Other SD servers using compatible API format

### Request Format

```json
{
  "prompt": "your prompt here",
  "negative_prompt": "negative prompt here",
  "steps": 4,
  "cfg_scale": 3.8,
  "width": 544,
  "height": 960,
  "samples": 1,
  "batch_size": 1,
  "seed": -1,
  "sampler_name": "euler",
  "restore_faces": false,
  "tiling": false,
  "enable_hr": false
}
```

### Response Format

```json
{
  "images": ["base64_encoded_image_data"],
  "parameters": {...},
  "info": "generation_info"
}
```

## Error Handling

The `SdServerImageGeneration` class handles:

- **Connection errors** - Server not running or unreachable
- **HTTP errors** - Invalid requests, server errors
- **Timeout errors** - Request exceeding timeout
- **Invalid response format** - Unexpected API response structure

## Advantages of SD Server

### Compared to SD CLI

| Feature | SD Server | SD CLI |
|---------|-----------|--------|
| **UI** | Full web interface | CLI only |
| **Queue Management** | Built-in queue | Manual |
| **Model Switching** | Easy UI switching | Manual path changes |
| **Extension Support** | Full extension support | Limited |
| **Monitoring** | Real-time progress | Log files |
| **Multiple Models** | Switch on-the-fly | Requires restart |

### Use Cases for SD Server

- **Production deployments** - Easier to manage and monitor
- **Multiple pipelines** - Share a single server instance
- **Model experimentation** - Switch models without code changes
- **UI-based generation** - Generate images directly in browser
- **Extension support** - Use ControlNet, LoRA, etc.

## Troubleshooting

### Server Not Available

```
sd_server_unavailable: SD server at http://localhost:1234 is not accessible
```

**Solution:**
1. Start your SD server (Automatic1111 or ComfyUI)
2. Ensure `--api` flag is enabled
3. Check URL and port in `.env` match your server
4. Verify firewall allows connections on port 1234

### Connection Refused

```
SD server connection error: Connection refused
```

**Solution:**
1. Check if server is running: `curl http://localhost:1234/sdapi/v1/options`
2. Verify server is listening on correct port
3. Check server logs for errors

### Slow Generation

```
SD server request timed out after 300s
```

**Solution:**
1. Increase `SD_SERVER_TIMEOUT_SECONDS` in `.env`
2. Reduce `SD_STEPS` or image resolution
3. Check GPU/CPU resources on server machine

### Invalid Response

```
image_generation_failed_for_scene_001: Unexpected image format in response
```

**Solution:**
1. Check SD server version compatibility
2. Verify API endpoint matches server type
3. Check server logs for errors

## Testing

### Test Server Connection

```bash
curl http://localhost:1234/sdapi/v1/options
```

Should return server options JSON.

### Test Image Generation

```bash
curl -X POST "http://localhost:1234/sdapi/v1/txt2img" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "a professional at a tidy desk",
    "negative_prompt": "blurry, low quality",
    "steps": 4,
    "width": 544,
    "height": 960
  }'
```

### Test Pipeline

```bash
cd /home/rafatz/projects/stoic-modernized

# Ensure SD server is running
# Configure .env with SD_SERVER_URL

# Run pipeline
python -m src.main run "your topic here" --mock

# Check generated images
ls output/jobs/<job_id>/images/
```

## Next Steps

1. Test SD server connection with your setup
2. Configure `.env` with your server URL
3. Run a test pipeline
4. Monitor logs for any issues

## Resources

- **Automatic1111 Web UI**: https://github.com/AUTOMATIC1111/stable-diffusion-webui
- **ComfyUI**: https://github.com/comfyanonymous/ComfyUI
- **SD API Docs**: https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/docs/API.md

---

**Integration Complete!** 🎉

The pipeline now supports SD server-based image generation, providing a more flexible and manageable image generation workflow.
