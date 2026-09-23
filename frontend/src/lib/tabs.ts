export type WorkspaceTab = 'overview' | 'findings' | 'values' | 'ask'

export const tabId = (id: WorkspaceTab) => `tab-${id}`
export const panelId = (id: WorkspaceTab) => `panel-${id}`
