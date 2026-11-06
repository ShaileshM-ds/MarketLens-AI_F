import { Link } from 'react-router-dom';
import { PageHeader } from './PageHeader';

export function NotFound() {
  return (
    <div className="stack-lg">
      <PageHeader title="Page not found" note="The address doesn't match any page." />
      <p>
        <Link to="/" className="btn btn--primary">
          Go to Overview
        </Link>
      </p>
    </div>
  );
}
