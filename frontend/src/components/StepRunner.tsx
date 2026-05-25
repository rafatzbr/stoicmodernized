import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';
import { Button, Stack, Typography } from '@mui/material';

const DEFAULT_STEPS = ['research', 'script', 'scene', 'tts', 'music', 'images', 'subtitles', 'render', 'metadata'];

type Props = {
  selectedJobId: string;
  selectedSteps: string[];
  isRunning: boolean;
  onToggleStep: (step: string) => void;
  onRunSteps: () => void;
};

export function StepRunner({ selectedJobId, selectedSteps, isRunning, onToggleStep, onRunSteps }: Props) {
  const hasSteps = selectedSteps.length > 0;

  return (
    <Stack spacing={3}>
      <Stack spacing={1}>
        <Typography variant="overline" color="text.secondary">
          PARTIAL RUNS
        </Typography>
        <Typography variant="h5">Run only what needs rerunning</Typography>
        <Typography variant="body2" color="text.secondary">
          {selectedJobId
            ? `Continuing ${selectedJobId}. Leave research off unless you want a new chain.`
            : 'No job selected yet. Include research if you want this to create a new job.'}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        {DEFAULT_STEPS.map((step) => {
          const active = selectedSteps.includes(step);
          return (
            <Button
              key={step}
              variant={active ? 'contained' : 'outlined'}
              color={active ? 'primary' : 'inherit'}
              onClick={() => onToggleStep(step)}
              sx={{ minWidth: 0 }}
            >
              {step.toUpperCase()}
            </Button>
          );
        })}
      </Stack>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} alignItems={{ xs: 'stretch', sm: 'center' }}>
        <Typography variant="caption" color="text.secondary" sx={{ minWidth: 120 }}>
          {selectedSteps.length} STEP{selectedSteps.length === 1 ? '' : 'S'} SELECTED
        </Typography>
        <Button variant="contained" startIcon={<PlayArrowRoundedIcon />} onClick={onRunSteps} disabled={!hasSteps || isRunning}>
          {isRunning ? 'RUN IN PROGRESS…' : 'RUN SELECTED STEPS'}
        </Button>
      </Stack>
    </Stack>
  );
}
