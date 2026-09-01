import { BuilderListScreen } from './screens/BuilderListScreen'
import { GameScreen } from './screens/GameScreen'
import { SessionsScreen } from './screens/SessionsScreen'
import { useHashRoute } from './useHashRoute'

export default function App() {
  const route = useHashRoute()

  if (route.name === 'game') return <GameScreen sessionId={route.id} />
  if (route.name === 'builderList') return <BuilderListScreen />
  return <SessionsScreen />
}
