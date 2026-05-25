import SaveRoundedIcon from '@mui/icons-material/SaveRounded';
import { Button, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useMemo, useState } from 'react';

type Props = {
  envContent: string;
  configContent: string;
  isLoading: boolean;
  onEnvChange: (value: string) => void;
  onConfigChange: (value: string) => void;
  onSaveEnv: () => void;
  onSaveConfig: () => void;
};

export function FileEditors({
  envContent,
  configContent,
  isLoading,
  onEnvChange,
  onConfigChange,
  onSaveEnv,
  onSaveConfig,
}: Props) {
  const [tab, setTab] = useState<'env' | 'config'>('env');

  const editor = useMemo(() => {
    if (tab === 'env') {
      return {
        title: '.env',
        description: 'Runtime environment values for the project.',
        content: envContent,
        onChange: onEnvChange,
        onSave: onSaveEnv,
        actionLabel: 'SAVE .ENV',
      };
    }

    return {
      title: 'src/config.py',
      description: 'Project config source. This writes directly to the file.',
      content: configContent,
      onChange: onConfigChange,
      onSave: onSaveConfig,
      actionLabel: 'SAVE CONFIG.PY',
    };
  }, [configContent, envContent, onConfigChange, onEnvChange, onSaveConfig, onSaveEnv, tab]);

  return (
    <Stack spacing={3}>
      <Stack spacing={1}>
        <Typography variant="overline" color="text.secondary">
          CONFIG
        </Typography>
        <Typography variant="h5">Inline editors</Typography>
        <Typography variant="body2" color="text.secondary">
          Useful for fast local tuning, but still sharp enough to be dangerous.
        </Typography>
      </Stack>

      <Tabs value={tab} onChange={(_, value: 'env' | 'config') => setTab(value)}>
        <Tab label=".env" value="env" />
        <Tab label="config.py" value="config" />
      </Tabs>

      <Stack spacing={1}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {editor.title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {editor.description}
        </Typography>
      </Stack>

      <TextField
        multiline
        minRows={18}
        fullWidth
        value={editor.content}
        onChange={(event) => editor.onChange(event.target.value)}
        placeholder={isLoading ? 'Loading…' : ''}
        disabled={isLoading}
        slotProps={{
          input: {
            sx: {
              fontFamily: 'Space Mono, ui-monospace, monospace',
              fontSize: 12,
              lineHeight: 1.8,
            },
          },
        }}
      />

      <Button variant="contained" onClick={editor.onSave} disabled={isLoading} startIcon={<SaveRoundedIcon />} sx={{ alignSelf: 'flex-start' }}>
        {editor.actionLabel}
      </Button>
    </Stack>
  );
}
