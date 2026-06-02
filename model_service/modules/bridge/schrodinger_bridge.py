import numpy as np
from scipy.spatial.distance import cdist

try:
    import ot
    POT_AVAILABLE = True
except ImportError:
    POT_AVAILABLE = False

print("POT_AVAILABLE:", POT_AVAILABLE)


class SchrodingerBridgeMapper:
    """Fit a Schrödinger bridge from humans to cats, then map new points."""

    def __init__(self, epsilon: float = None, eps_quantile=0.05, max_iter: int = 1000, tol: float = 1e-9):
        self.epsilon = epsilon
        self.eps_quantile = eps_quantile
        self.max_iter = max_iter
        self.tol = tol
        self.cats = None           # target embeddings
        self.v_ = None             # Sinkhorn target scaling (length m)
        self.epsilon_used_ = None  # final epsilon after fit

    def fit_transform(self, humans: np.ndarray, cats: np.ndarray):
        """Compute the bridge between the original human and cat distributions."""
        n, d = humans.shape
        m, _ = cats.shape

        mu = np.ones(n) / n
        nu = np.ones(m) / m

        # cost = squared Euclidean distances
        C = cdist(humans, cats, 'sqeuclidean')

        if self.epsilon is None:
            # For each human, find the distance to its 'eps_quantile'‑closest cat
            sorted_C = np.sort(C, axis=1)                  # (n, m)
            k = max(1, int(self.eps_quantile * m))          # column index
            nearest_dists = sorted_C[:, k]                  # shape (n,)
            self.epsilon_used_ = np.median(nearest_dists)
        else:
            self.epsilon_used_ = self.epsilon

        print("Epsilon used:", self.epsilon_used_)

        # Run Sinkhorn to obtain the target scaling v
        if POT_AVAILABLE:
            # POT returns the transport plan, we need the scalings.
            # We can obtain them by calling ot.sinkhorn with log=True
            plan, log = ot.sinkhorn(
                mu, nu, C, self.epsilon_used_,
                method='sinkhorn', numItermax=self.max_iter,
                stopThr=self.tol, log=True, verbose=False
            )
            # log['u'] and log['v'] are the Sinkhorn scalings (n, ) and (m, )
            v = log['v']
        else:
            # manual Sinkhorn with scalings
            def sinkhorn_manual(C, mu, nu, eps, max_iter, tol):
                K = np.exp(-C / eps)
                u = np.ones(len(mu))
                v = np.ones(len(nu))
                for it in range(max_iter):
                    u_prev = u.copy()
                    u = mu / (K.dot(v) + 1e-16)
                    v = nu / (K.T.dot(u) + 1e-16)
                    if np.max(np.abs(u - u_prev)) < tol:
                        break
                plan = np.diag(u).dot(K).dot(np.diag(v))
                return plan, u, v

            plan, u, v = sinkhorn_manual(C, mu, nu, self.epsilon_used_,
                                   self.max_iter, self.tol)

        mapped_humans = n * plan.dot(cats)
        self.cats = cats
        self.v_ = v
        return mapped_humans

    def transform(self, humans_new: np.ndarray) -> np.ndarray:
        """Map a batch of new human embeddings to the cat domain."""
        if self.cats is None or self.v_ is None:
            raise RuntimeError("The mapper must be fitted before transform.")

        # distances to all cats
        C_new = cdist(humans_new, self.cats, 'sqeuclidean')
        # kernel with the same epsilon
        K_new = np.exp(-C_new / self.epsilon_used_)
        # conditional weights: proportional to K(x, y_j) * v_j
        weights = K_new * self.v_[np.newaxis, :]   # (k, m)
        weights /= weights.sum(axis=1, keepdims=True)  # row‑normalise
        # barycentric projection
        mapped = weights.dot(self.cats)            # (k, d)
        return mapped

    def find_closest(self, cat_emb: np.ndarray) -> np.ndarray:
        C = cdist(cat_emb, self.cats, 'sqeuclidean')
        closest_idx = np.argmin(C, axis=1)
        return closest_idx

