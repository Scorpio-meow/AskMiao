
import { Navigate, useLocation, useOutletContext } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Forbidden from './Forbidden';
export const PrivateRoute = ({ element }) => {
  const location = useLocation();
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return element;
};
export const AdminRoute = ({ element }) => {
  const location = useLocation();
  const user = useOutletContext();
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  if (!user?.is_admin) {
    return <Forbidden />;
  }
  return element;
};
export const PublicRoute = ({ element }) => {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  return element;
}; export default PrivateRoute;
