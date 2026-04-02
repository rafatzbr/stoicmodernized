import ChecklistRoundedIcon from '@mui/icons-material/ChecklistRounded';
import {
  Button,
  Card,
  CardContent,
  Chip,
  FormControlLabel,
  Stack,
  Switch,
  Typography,
} from '@mui/material';

const DEFAULT_STEPS = ['research', 'script', 'scene', 'tts', 'images', 'subtitles', 'render', 'metadata'];

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
    <Card>
      <CardContent>
        <Stack spacing={2.5}>
          <div>
            <Typography variant="overline" color="secondary.main">
              Partial runs
            </Typography>
            <Typography variant="h6">Run selected steps</Typography>
            <Typography variant="body2" color="text.secondary">
              {selectedJobId
                ? `Continuing job ${selectedJobId}`
                : 'No job selected. Including research will create a new job chain.'}
            </Typography>
          </div>

          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip label={`Selected: ${selectedSteps.length}`} size="small" color={hasSteps ? 'secondary' : 'default'} />
            <Chip label={selectedJobId ? 'Existing job' : 'New job path'} size="small" variant="outlined" />
          </Stack>

          <Stack spacing={0.5}>
            {DEFAULT_STEPS.map((step) => (
              <FormControlLabel
                key={step}
                control={<Switch checked={selectedSteps.includes(step)} onChange={() => onToggleStep(step)} />}
                label={step}
                sx={{
                  m: 0,
                  px: 1.5,
                  py: 0.5,
                  borderRadius: 2,
                  border: '1px solid',
                  borderColor: selectedSteps.includes(step) ? 'secondary.main' : 'divider',
                  bgcolor: selectedSteps.includes(step) ? 'action.selected' : 'transparent',
                }}
              />
            ))}
          </Stack>

          <Button
            variant="outlined"
            startIcon={<ChecklistRoundedIcon />}
            onClick={onRunSteps}
            disabled={!hasSteps || isRunning}
          >
            {isRunning ? 'Run in progress…' : 'Run selected steps'}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
