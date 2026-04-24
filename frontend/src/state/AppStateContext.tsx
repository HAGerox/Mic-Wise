import { createContext, useContext, useMemo, useReducer } from 'react';
import type { Dispatch, PropsWithChildren } from 'react';

import {
  appStateReducer,
  initialAppState,
  type AppState,
  type AppStateAction,
} from './appStateReducer';

interface AppStateContextValue {
  state: AppState;
  dispatch: Dispatch<AppStateAction>;
}

const AppStateContext = createContext<AppStateContextValue | null>(null);

export function AppStateProvider({ children }: PropsWithChildren): JSX.Element {
  const [state, dispatch] = useReducer(appStateReducer, initialAppState);
  const value = useMemo(() => ({ state, dispatch }), [state, dispatch]);
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateContextValue {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error('useAppState must be used inside AppStateProvider');
  }
  return context;
}
