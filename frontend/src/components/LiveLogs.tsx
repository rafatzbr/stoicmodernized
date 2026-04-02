import TerminalRoundedIcon from '@mui/icons-material/TerminalRounded';
import { Box, Button, Card, CardContent, Chip, Divider, Stack, Typography } from '@mui/material';
import type { RunState } from '../types';

type Props = {
  runState: RunState | null;
  onClear: () => void;
};

export function LiveLogs({ runState, onClear }: Props) {
  const statusLabel = !runState ? 'idle' : runState.running ? 'running' : runState.returncode === 0 ? 'completed' : 'stopped';

  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={2}>
            <Box>
              <Typography variant="overline" color="secondary.main">
                Runtime
              </Typography>
              <Typography variant="h6">Live run logs</Typography>
            </Box>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip label={statusLabel} size="small" color={runState?.running ? 'warning' : runState ? 'success' : 'default'} />
              <Button size="small" onClick={onClear} disabled={!runState}>
                Clear
              </Button>
            </Stack>
          </Stack>

          <Divider />

          {runState?.cmd?.length ? (
            <Typography variant="caption" color="text.secondary">
              {runState.cmd.join(' ')}
            </Typography>
          ) : null}

          <Box
            component="pre"
            sx={{
              mb: 0,
              p: 2,
              minHeight: 260,
              maxHeight: 420,
              overflow: 'auto',
              borderRadius: 2,
              bgcolor: 'rgba(7, 10, 19, 0.92)',
              color: '#d8e1ff',
              border: '1px solid',
              borderColor: 'divider',
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
              fontSize: 13,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {runState?.lines.length ? runState.lines.join('\n') : 'No active run. Start a job to stream logs here.'}
          </Box>

          {!runState && (
            <Stack direction="row" spacing={1} alignItems="center">
              <TerminalRoundedIcon fontSize="small" color="disabled" />
              <Typography variant="body2" color="text.secondary">
                Log stream will appear once a run starts.
              </Typography>
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
