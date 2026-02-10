// 主应用入口
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import MainLayout from './components/Layout';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Register from './pages/Login/Register';
import Dashboard from './pages/Dashboard';
import ProjectList from './pages/Project';
import ProjectDetail from './pages/Project/Detail';
import ChatPage from './pages/Chat';
import ExternalSearchPage from './pages/ExternalSearch';
import './App.css';

function App() {
  return (
    <ErrorBoundary>
      <ConfigProvider locale={zhCN}>
        <BrowserRouter>
          <Routes>
            {/* 公开路由 */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* 受保护路由 */}
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <MainLayout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="projects" element={<ProjectList />} />
              <Route path="project/:id" element={<ProjectDetail />} />
              <Route path="chat" element={<ChatPage />} />
              <Route path="chat/:projectId" element={<ChatPage />} />
              <Route path="search" element={<ExternalSearchPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ConfigProvider>
    </ErrorBoundary>
  );
}

export default App;
