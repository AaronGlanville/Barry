from abc import ABC

import numpy as np
from scipy.integrate import trapz
from scipy.interpolate import interp1d, splev, splrep


class PowerToCorrelation(ABC):
    """ Generic class for converting power spectra to correlation functions

    Using a class based method as there might be multiple implementations and
    some of the implementations have state.
    """

    def __call__(self, ks, pk, ss):
        """ Generates the correlation function

        Parameters
        ----------
        ks : np.ndarray
            The k values for the power spectrum data. *Assumed to be in log space*
        pk : np.ndarray
            The P(k) values
        ss : np.nparray
            The distances to calculate xi(s) at.

        Returns
        -------
        xi : np.ndarray
            The correlation function at the specified distances
        """
        raise NotImplementedError()


class PowerToCorrelationGauss(PowerToCorrelation):
    """ A pk2xi implementation using manual numeric integration with Gaussian dampening factor
    """

    def __init__(self, ks, interpolateDetail=2, a=0.25):
        super().__init__()
        self.ks = ks
        self.ks2 = np.logspace(np.log(np.min(ks)), np.log(np.max(ks)), interpolateDetail * ks.size, base=np.e)
        self.precomp = self.ks2 * np.exp(-self.ks2 * self.ks2 * a * a) / (2 * np.pi * np.pi)  # Precomp a bunch of things

    def __call__(self, ks, pks, ss):
        pks2 = interp1d(ks, pks, kind="linear")(self.ks2)
        # Set up output array
        xis = np.zeros(ss.size)

        # Precompute k^2 and gauss (note missing a ks factor below because integrating in log space)
        kkpks = self.precomp * pks2

        # Iterate over all values in desired output array of distances (s)
        for i, s in enumerate(ss):
            integrand = kkpks * np.sin(self.ks2 * s) / s
            xis[i] = trapz(integrand, self.ks2)

        return xis


class PowerToCorrelationFT(PowerToCorrelation):
    """ A pk2xi implementation utilising the Hankel library to use explicit FFT.
    """

    def __init__(self, num_nodes=None, h=0.001):
        """

        Parameters
        ----------
         num_nodes : int, optional
            Number of nodes in FFT
        h : float, optional
            Step size of integration
        """
        from hankel import SymmetricFourierTransform

        self.ft = SymmetricFourierTransform(ndim=3, N=num_nodes, h=h)

    def __call__(self, ks, pk, ss):
        pkspline = splrep(ks, pk)
        f = lambda k: splev(k, pkspline)
        xi = self.ft.transform(f, ss, inverse=True, ret_err=False)
        return xi


if __name__ == "__main__":
    from barry.cosmology import CambGenerator

    # camb = CambGenerator(h0=70.0)
    camb = CambGenerator(om_resolution=10, h0_resolution=1)
    ks = camb.ks
    r_s, pklin, _ = camb.get_data(0.3, 0.70)

    ss = np.linspace(30, 200, 85)

    # This code tests the impact the lower k bound has on converting to correlation plot
    thresh = 100
    pk2xi_1 = PowerToCorrelationGauss(ks, interpolateDetail=10, a=1)
    pk2xi_2 = PowerToCorrelationGauss(ks[ks < thresh], interpolateDetail=10, a=1)
    import matplotlib.pyplot as plt

    xi1 = pk2xi_1.__call__(ks, pklin, ss)
    xi2 = pk2xi_2.__call__(ks[ks < thresh], pklin[ks < thresh], ss)
    fig, ax = plt.subplots(nrows=2)
    ax[0].plot(ss, xi1)
    ax[0].plot(ss, xi2)
    ax[1].plot(ss, 100 * (xi1 - xi2) / xi1)
    plt.show()

    pk2xi_good = PowerToCorrelationGauss(ks, interpolateDetail=10, a=1)
    pk2xi_gauss = PowerToCorrelationGauss(ks, interpolateDetail=2, a=0.25)
    pk2xi_ft = PowerToCorrelationFT()

    if False:
        import timeit

        n = 200

        def test():
            pk2xi_gauss.__call__(ks, pklin, ss)

        print("Gauss method: %.2f milliseconds" % (timeit.timeit(test, number=n) * 1000 / n))

        def test2():
            pk2xi_ft.__call__(ks, pklin, ss)

        print("FT method: %.2f milliseconds" % (timeit.timeit(test2, number=n) * 1000 / n))

    if False:
        import matplotlib.pyplot as plt

        xi1 = pk2xi_gauss.__call__(ks[ks < 1], pklin, ss)
        xi2 = pk2xi_ft.__call__(ks, pklin, ss)
        xi_good = pk2xi_good.__call__(ks, pklin, ss)

        fig, ax = plt.subplots(nrows=2, sharex=True)
        ax[0].plot(ss, xi_good, ".", c="k")
        ax[0].plot(ss, xi1, ".", c="b", label="Gauss")
        ax[0].plot(ss, xi2, ".", c="r", label="FT")
        ax[0].legend()
        ax[1].plot(ss, 100000 * (xi_good - xi1), ".", c="b")
        ax[1].plot(ss, 100000 * (xi_good - xi2), ".", c="r")
        ax[1].axhline(0)
        ax[1].set_xlabel("Dist")
        ax[1].set_ylabel("100 000 times diff")
        ax[0].set_ylabel("xi(s)")
        plt.show()
