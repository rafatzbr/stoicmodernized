import OpenInFullRoundedIcon from '@mui/icons-material/OpenInFullRounded';
import TerminalRoundedIcon from '@mui/icons-material/TerminalRounded';
import { Box, Button, Card, CardContent, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Divider, Stack, Typography } from '@mui/material';
import { useState } from 'react';
import type { RunState } from '../types';

type Props = {
  runState: RunState | null;
  onClear: () => void;
};

function LogsContent({ runState, expanded = false }: { runState: RunState | null; expanded?: boolean }) {
  return (
    <>
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
          minHeight: expanded ? 420 : 260,
          maxHeight: expanded ? '70vh' : 420,
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
    </>
  );
}

export function LiveLogs({ runState, onClear }: Props) {
  const statusLabel = !runState ? 'idle' : runState.running ? 'running' : runState.returncode === 0 ? 'completed' : 'stopped';
  const [open, setOpen] = useState(false);

  return (
    <>
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
                <Button size="small" startIcon={<OpenInFullRoundedIcon />} onClick={() => setOpen(true)}>
                  Pop out
                </Button>
                <Button size="small" onClick={onClear} disabled={!runState}>
                  Clear
                </Button>
              </Stack>
            </Stack>

            <Divider />
            <LogsContent runState={runState} />
          </Stack>
        </CardContent>
      </Card>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Live run logs</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <LogsContent runState={runState} expanded />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClear} disabled={!runState}>Clear</Button>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
