import SaveRoundedIcon from '@mui/icons-material/SaveRounded';
import {
  Button,
  Card,
  CardContent,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
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
        title: '.env variables',
        description: 'Environment values used by the local pipeline runtime.',
        content: envContent,
        onChange: onEnvChange,
        onSave: onSaveEnv,
        actionLabel: 'Save .env',
      };
    }

    return {
      title: 'Config file',
      description: 'Direct edit of src/config.py for internal tuning and overrides.',
      content: configContent,
      onChange: onConfigChange,
      onSave: onSaveConfig,
      actionLabel: 'Save config.py',
    };
  }, [configContent, envContent, onConfigChange, onEnvChange, onSaveConfig, onSaveEnv, tab]);

  return (
    <Card>
      <CardContent>
        <Stack spacing={2.5}>
          <div>
            <Typography variant="overline" color="secondary.main">
              Configuration
            </Typography>
            <Typography variant="h6">Editors</Typography>
          </div>

          <Tabs value={tab} onChange={(_, value: 'env' | 'config') => setTab(value)}>
            <Tab label=".env" value="env" />
            <Tab label="config.py" value="config" />
          </Tabs>

          <div>
            <Typography variant="subtitle1">{editor.title}</Typography>
            <Typography variant="body2" color="text.secondary">
              {editor.description}
            </Typography>
          </div>

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
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  fontSize: 13,
                  lineHeight: 1.6,
                },
              },
            }}
          />

          <Button
            variant="contained"
            onClick={editor.onSave}
            disabled={isLoading}
            startIcon={<SaveRoundedIcon />}
            sx={{ alignSelf: 'flex-start' }}
          >
            {editor.actionLabel}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
