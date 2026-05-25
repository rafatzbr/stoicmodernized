import OpenInFullRoundedIcon from '@mui/icons-material/OpenInFullRounded';
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { useState } from 'react';
import type { RunState } from '../types';

type Props = {
  runState: RunState | null;
  onClear: () => void;
};

function statusLabel(runState: RunState | null) {
  if (!runState) return 'IDLE';
  if (runState.running) return 'RUNNING';
  if (runState.returncode === 0) return 'COMPLETE';
  return 'FAILED';
}

function LogsBody({ runState, expanded = false }: { runState: RunState | null; expanded?: boolean }) {
  return (
    <Stack spacing={1.5}>
      {runState?.cmd?.length ? (
        <Typography variant="caption" color="text.secondary" sx={{ wordBreak: 'break-word' }}>
          {runState.cmd.join(' ')}
        </Typography>
      ) : null}
      <Box
        component="pre"
        sx={{
          m: 0,
          p: 2,
          minHeight: expanded ? 460 : 280,
          maxHeight: expanded ? '72vh' : 360,
          overflow: 'auto',
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: '#050505',
          color: '#f5f5f5',
          fontFamily: 'Space Mono, ui-monospace, monospace',
          fontSize: 12,
          lineHeight: 1.75,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {runState?.lines.length ? runState.lines.join('\n') : '[NO ACTIVE RUN]'}
      </Box>
    </Stack>
  );
}

export function LiveLogs({ runState, onClear }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Stack spacing={3}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-end" spacing={2}>
          <Box>
            <Typography variant="overline" color="text.secondary">
              LIVE LOGS
            </Typography>
            <Typography variant="h5">{statusLabel(runState)}</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" size="small" startIcon={<OpenInFullRoundedIcon />} onClick={() => setOpen(true)}>
              EXPAND
            </Button>
            <Button variant="text" size="small" onClick={onClear} disabled={!runState}>
              CLEAR
            </Button>
          </Stack>
        </Stack>
        <LogsBody runState={runState} />
      </Stack>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Live logs</DialogTitle>
        <DialogContent dividers>
          <LogsBody runState={runState} expanded />
        </DialogContent>
        <DialogActions>
          <Button onClick={onClear} disabled={!runState}>Clear</Button>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
