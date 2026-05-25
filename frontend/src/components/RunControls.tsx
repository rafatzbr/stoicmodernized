import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import {
  Button,
  FormControl,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

const channelOptions = [
  {
    value: 'stoic-modernized',
    label: 'Stoic Modernized',
    note: 'Calm, practical philosophy for work.',
  },
  {
    value: 'ai-signal',
    label: 'The AI Signal',
    note: 'Fast AI-news coverage, tight and factual.',
  },
];
const providerOptions = ['edge', 'local', 'elevenlabs', 'voxcpm'];
const videoModeOptions = ['short', 'long'];
const platformOptions = ['auto', 'youtube', 'tiktok'];
const rendererOptions = [
  { value: 'ffmpeg', label: 'FFMPEG', note: 'Fastest' },
  { value: 'remotion', label: 'REMOTION', note: 'Best visuals' },
  { value: 'both', label: 'BOTH', note: 'Compare renders' },
];

type Props = {
  topic: string;
  channel: string;
  videoMode: string;
  provider: string;
  platform: string;
  renderer: string;
  isStarting: boolean;
  isSuggestingTopic?: boolean;
  onTopicChange: (value: string) => void;
  onChannelChange: (value: string) => void;
  onVideoModeChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onPlatformChange: (value: string) => void;
  onRendererChange: (value: string) => void;
  onSuggestTopic: () => void;
  onStart: () => void;
};

export function RunControls({
  topic,
  channel,
  videoMode,
  provider,
  platform,
  renderer,
  isStarting,
  isSuggestingTopic = false,
  onTopicChange,
  onChannelChange,
  onVideoModeChange,
  onProviderChange,
  onPlatformChange,
  onRendererChange,
  onSuggestTopic,
  onStart,
}: Props) {
  const canStart = (channel === 'ai-signal' || topic.trim().length > 0) && !isStarting;
  const activeChannel = channelOptions.find((option) => option.value === channel) ?? channelOptions[0];
  const placeholder = 'e.g. workplace stress, boundaries, calm ambition';

  return (
    <Stack spacing={3}>
      <Stack spacing={1}>
        <Typography variant="overline" color="text.secondary">
          RUN
        </Typography>
        <Typography variant="h5">Start a clean pipeline run</Typography>
        <Typography variant="body2" color="text.secondary">
          Pick the channel first. The rest of the controls follow from that choice.
        </Typography>
      </Stack>

      <Stack spacing={1.25}>
        <Typography variant="overline" color="text.secondary">
          CHANNEL
        </Typography>
        <FormControl fullWidth size="small">
          <Select value={channel} onChange={(event) => onChannelChange(String(event.target.value))}>
            {channelOptions.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                <Stack spacing={0.25}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {option.label}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {option.note}
                  </Typography>
                </Stack>
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <Typography variant="body2" color="text.secondary">
          {activeChannel.note}
        </Typography>
      </Stack>

      {channel === 'stoic-modernized' ? (
        <Stack spacing={1.25}>
          <Typography variant="overline" color="text.secondary">
            TOPIC
          </Typography>
          <TextField
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder={placeholder}
            fullWidth
            multiline
            minRows={3}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} alignItems={{ xs: 'stretch', sm: 'center' }}>
            <Button
              variant="outlined"
              startIcon={<AutoAwesomeRoundedIcon />}
              onClick={onSuggestTopic}
              disabled={isSuggestingTopic || isStarting}
            >
              {isSuggestingTopic ? 'ASKING LOCAL MODEL…' : 'SUGGEST WITH LOCAL MODEL'}
            </Button>
            <Typography variant="caption" color="text.secondary">
              No mock suggestions. This only uses the real local model.
            </Typography>
          </Stack>
        </Stack>
      ) : null}

      <Stack spacing={1.25}>
        <Typography variant="overline" color="text.secondary">
          OUTPUT
        </Typography>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25}>
          <FormControl fullWidth size="small">
            <Select value={videoMode} onChange={(event) => onVideoModeChange(String(event.target.value))}>
              {videoModeOptions.map((option) => (
                <MenuItem key={option} value={option}>
                  {option.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth size="small">
            <Select value={platform} onChange={(event) => onPlatformChange(String(event.target.value))}>
              {platformOptions.map((option) => (
                <MenuItem key={option} value={option}>
                  {option.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.25}>
          <FormControl fullWidth size="small">
            <Select value={provider} onChange={(event) => onProviderChange(String(event.target.value))}>
              {providerOptions.map((option) => (
                <MenuItem key={option} value={option}>
                  {option.toUpperCase()}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <FormControl fullWidth size="small">
            <Select value={renderer} onChange={(event) => onRendererChange(String(event.target.value))}>
              {rendererOptions.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label} · {option.note}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </Stack>

      <Button
        variant="contained"
        size="large"
        startIcon={<PlayArrowRoundedIcon />}
        onClick={onStart}
        disabled={!canStart}
        sx={{ alignSelf: 'flex-start', minWidth: 220 }}
      >
        {isStarting ? 'STARTING…' : 'START FULL RUN'}
      </Button>
    </Stack>
  );
}
