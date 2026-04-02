import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import RocketLaunchRoundedIcon from '@mui/icons-material/RocketLaunchRounded';
import {
  Button,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

const providerOptions = ['edge', 'local', 'elevenlabs'];
const videoModeOptions = ['short', 'long'];

type Props = {
  topic: string;
  videoMode: string;
  provider: string;
  isStarting: boolean;
  onTopicChange: (value: string) => void;
  onVideoModeChange: (value: string) => void;
  onProviderChange: (value: string) => void;
  onStart: () => void;
};

export function RunControls({
  topic,
  videoMode,
  provider,
  isStarting,
  onTopicChange,
  onVideoModeChange,
  onProviderChange,
  onStart,
}: Props) {
  const canStart = topic.trim().length > 0 && !isStarting;

  return (
    <Card>
      <CardContent>
        <Stack spacing={2.5}>
          <div>
            <Typography variant="overline" color="secondary.main">
              Full pipeline
            </Typography>
            <Typography variant="h6">Start full generation run</Typography>
            <Typography variant="body2" color="text.secondary">
              Kick off research through render using the current topic and provider.
            </Typography>
          </div>

          <TextField
            label="Topic"
            value={topic}
            onChange={(event) => onTopicChange(event.target.value)}
            placeholder="e.g. workplace stress, boundaries, calm ambition"
            fullWidth
          />

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <FormControl fullWidth>
              <InputLabel id="video-mode-label">Video mode</InputLabel>
              <Select
                labelId="video-mode-label"
                value={videoMode}
                label="Video mode"
                onChange={(event) => onVideoModeChange(String(event.target.value))}
              >
                {videoModeOptions.map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <FormControl fullWidth>
              <InputLabel id="provider-label">TTS provider</InputLabel>
              <Select
                labelId="provider-label"
                value={provider}
                label="TTS provider"
                onChange={(event) => onProviderChange(String(event.target.value))}
              >
                {providerOptions.map((option) => (
                  <MenuItem key={option} value={option}>
                    {option}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          <Button
            variant="contained"
            size="large"
            startIcon={isStarting ? <RocketLaunchRoundedIcon /> : <PlayArrowRoundedIcon />}
            onClick={onStart}
            disabled={!canStart}
          >
            {isStarting ? 'Starting run…' : 'Start full run'}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
