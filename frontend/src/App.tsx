import { ChatPage } from './pages/ChatPage';
import type { Services } from './services/types';

export function App({ services }: { services: Services }) {
  return <ChatPage services={services} />;
}
