import { createElement, useCallback, useState, type CSSProperties } from 'react';

const NS = 'verge-browser';
const KIND = 'verge-browser';
const TYPE_ID = 'dsh-plugin-verge-browser/session';
const SESSION_FRAME = '/verge-browser/session/';

/** Client services this tab needs: slot hosting, copy, and the tab-type registry. */
export const inject = ['slots', 'locale', 'sidebarRightTabs'];

const zh = {
  'type.label': 'Verge 浏览器',
  'guide.title': 'Verge 浏览器',
  'guide.description': '显示已连接的远程浏览器，可人工操作',
  reload: '重新连接',
  frame: 'Verge 远程浏览器画面',
};
const en = {
  'type.label': 'Verge Browser',
  'guide.title': 'Verge Browser',
  'guide.description': 'Show the attached remote browser for manual control',
  reload: 'Reconnect',
  frame: 'Verge remote browser',
};

interface FrameProps {
  useTabInfo: () => { tab: { id: string } };
  t: (key: string) => string;
}

const styles: Record<string, CSSProperties> = {
  root: { display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 },
  bar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '5px 10px', flex: 'none',
    borderBottom: '1px solid var(--dsw-alias-border-l3, rgba(128,128,128,.25))',
    color: 'var(--dsw-alias-label-secondary, inherit)', fontSize: 12,
  },
  grow: { flex: 1 },
  button: {
    font: 'inherit', fontSize: 12, padding: '2px 8px', cursor: 'pointer', borderRadius: 6,
    border: '1px solid var(--dsw-alias-border-l3, rgba(128,128,128,.3))',
    background: 'transparent', color: 'inherit',
  },
  frame: { flex: 1, minHeight: 0, width: '100%', border: 0, background: '#000' },
};

/** Render the attached Verge session; each revision asks the host route for a fresh ticket. */
function VergeFrame({ useTabInfo, t }: FrameProps) {
  const { tab } = useTabInfo();
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  return createElement('div', { style: styles.root },
    createElement('div', { style: styles.bar },
      createElement('span', null, t('type.label')),
      createElement('span', { style: styles.grow }),
      createElement('button', { type: 'button', style: styles.button, onClick: reload }, t('reload'))),
    createElement('iframe', {
      key: revision,
      src: `${SESSION_FRAME}?tab=${encodeURIComponent(tab.id)}&revision=${revision}`,
      title: t('frame'),
      style: styles.frame,
      // The session keeps its own cookies and WebSocket; the host route supplies the ticket.
      allow: 'clipboard-read; clipboard-write',
    }));
}

interface ClientContext {
  effect(run: () => unknown, label: string): void;
  locale: {
    bind(namespace: string): (key: string) => string;
    register(namespace: string, copy: { zh: Record<string, string>; en: Record<string, string> }): unknown;
  };
  sidebarRightTabs: {
    register(definition: {
      id: string;
      kind: string;
      multiple: boolean;
      title: () => string;
      guide: { id: string; order: number; title: () => string; description: () => string }[];
    }): unknown;
  };
  slots: {
    inject(slot: string, run: () => unknown): unknown;
    register(options: { name: string; key: string; locale: string }, component: (props: FrameProps) => unknown): unknown;
  };
}

export function apply(ctx: ClientContext): void {
  const t = ctx.locale.bind(NS);
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), 'verge-browser: copy');
  ctx.effect(() => ctx.sidebarRightTabs.register({
    id: TYPE_ID,
    kind: KIND,
    multiple: true,
    title: () => t('type.label'),
    guide: [{
      id: 'session',
      order: 20,
      title: () => t('guide.title'),
      description: () => t('guide.description'),
    }],
  }), 'verge-browser: tab type');
  // The pane slot is declared by the sidebar inside its own activation chain, so wait for it.
  ctx.effect(() => ctx.slots.inject('sidebar.right.pane.tab', () => ctx.slots.register({
    name: 'sidebar.right.pane.tab',
    key: TYPE_ID,
    locale: NS,
  }, VergeFrame)), 'verge-browser: tab body');
}
