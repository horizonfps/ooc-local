import { SessionsScreen } from './screens/SessionsScreen'
import { useHashRoute } from './useHashRoute'

// The game screen (#/session/:id) ships with TCK-012; until then this
// route falls back to the sessions list, same as an unknown hash.
export default function App() {
  useHashRoute()

  return <SessionsScreen />
}
