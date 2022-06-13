import numpy as np
import matplotlib.pyplot as plt
import astropy.units as u

from . import FermiAnalysis, VeritasAnalysis
from ..utils import logger
from .. import utils

from gammapy.datasets import Datasets
from gammapy.modeling import Fit
import gammapy.modeling.models as gammapy_model
from gammapy.estimators import FluxPointsEstimator


class JointAnalysis:
    
    def __init__(self, veritas = "initial", fermi = "initlal", verbosity=1):
        self._verbosity = verbosity
        self._logging = logger(self.verbosity)
        self._logging.info("Initializing the joint-fit analysis...")
        self._outdir = "./joint/"

        if type(veritas) == str:
            self.veritas = VeritasAnalysis(veritas)
        elif hasattr(veritas, "datasets"):
            self._logging.info("VERITAS datasets is imported.")
            self.veritas = veritas
        else:
            return
        
        if type(fermi) == str:
            self.fermi = FermiAnalysis(fermi, construct_dataset=True)
        elif hasattr(fermi, "datasets"):
            self._logging.info("Fermi-LAT datasets is imported.")
            self.fermi = fermi
        else:
            return
        
        self._logging.info("Constructing a joint datasets")
        self._construct_joint_datasets()
        self._logging.info("Completed.")
        
    
    def _construct_joint_datasets(self, default_model="VERITAS"):
        vts_model = self.veritas.stacked_dataset.models[0]
        self.veritas.stacked_dataset.models = self._find_target_model()
        self.datasets = Datasets([self.fermi.datasets, self.veritas.stacked_dataset])
        if default_model:
            self.datasets.models[self.fermi.target_name].spectral_model = vts_model.spectral_model
        
        self.datasets.models[self.fermi.target_name]._name = self.target_name
        
    def _find_target_model(self):
        target_pos = self.fermi.datasets.models[self.fermi.target_id].spatial_model.position
        th2cut = self.veritas._on_region.radius.value

        models = []
        for model in self.fermi.datasets.models:
            if model.name != 'galdiff' and model.name != 'isodiff':
                if target_pos.separation(model.spatial_model.position).deg < th2cut:
                    models.append(model)
        return models
    
    def fit(self):

        self._logging.info("Start fitting...")

        joint_fit = Fit()
        self.fit_results = joint_fit.run(self.datasets)

        if self.fit_results.success:
            self._logging.info("Fit successfully.")
        else:
            self._logging.error("Fit fails.")
        
    def sed_plot(self, fermi=True, veritas=True, joint=True,**kwargs):

        if fermi and not(hasattr(self.fermi, "output")):
            self.fermi.simple_analysis("sed")
        if veritas and not(hasattr(self.veritas, "_flux_points_dataset")):
            self.veritas.simple_analysis()
        if joint and not(hasattr(self, "fit_results")):
            fit = False
        else:
            fit = True

        cmap = plt.get_cmap("tab10")
        i = 0

        if joint:
            if fit:
                #if not(hasattr(self, "_flux_points_dataset")):
                #    self.analysis()

                #jf = self._flux_points_dataset
                #energy_bounds = [100 * u.MeV, 30 * u.TeV]
                #jf.data.plot(sed_type="e2dnde", color = cmap(i))

                jf_model = jf.models[0].spectral_model
                jf_model.plot(energy_bounds=energy_bounds, sed_type="e2dnde", color=cmap(i), label="VERITAS")
                jf_model.plot_error(energy_bounds=energy_bounds, 
                                         sed_type="e2dnde", alpha=0.2, color="k")
            else:
                energy_bounds = [100 * u.MeV, 30 * u.TeV]
                jf_model = self.datasets.models[self.target_id].spectral_model
                
                if fit:
                    jf_model.plot(energy_bounds=energy_bounds, sed_type="e2dnde", color=cmap(i), label=self.target_name, ls="-")
                    jf_model.plot_error(energy_bounds=energy_bounds, 
                                         sed_type="e2dnde", alpha=0.2, color="k")
                else:
                    jf_model.plot(energy_bounds=energy_bounds, sed_type="e2dnde", color=cmap(i), label="Before fit", ls="--")
            i+=1

        if veritas:
            
            vts = self.veritas._flux_points_dataset
            energy_bounds = vts._energy_bounds
            vts.data.plot(sed_type="e2dnde", color = cmap(i), label="VERITAS")

            if not(fit):
                veritas_model = vts.models[0].spectral_model
                veritas_model.plot(energy_bounds=energy_bounds, sed_type="e2dnde", color=cmap(i))
                veritas_model.plot_error(energy_bounds=energy_bounds, 
                                         sed_type="e2dnde", alpha=0.2, color="k")
            i+=1

        if fermi:
            fermi_model = self.fermi.output["sed"]['model_flux']

            m_engs = 10**fermi_model['log_energies']
            to_TeV = 1e-6

            e2 = m_engs**2.*utils.MeV2Erg

            sed = self.fermi.output["sed"]
            ul_ts_threshold = kwargs.pop('ul_ts_threshold', 4)
            m = sed['ts'] < ul_ts_threshold
            x = sed['e_ctr']*to_TeV
            y = sed['e2dnde']*utils.MeV2Erg

            yerr = sed['e2dnde_err']*utils.MeV2Erg
            yerr_lo = sed['e2dnde_err_lo']*utils.MeV2Erg
            yerr_hi = sed['e2dnde_err_hi']*utils.MeV2Erg
            yul = sed['e2dnde_ul95']*utils.MeV2Erg
            delo = sed['e_ctr'] - sed['e_min']
            dehi = sed['e_max'] - sed['e_ctr']
            xerr0 = np.vstack((delo[m], dehi[m]))*to_TeV
            xerr1 = np.vstack((delo[~m], dehi[~m]))*to_TeV

            plt.errorbar(x[~m], y[~m], xerr=xerr1, label="Fermi-LAT",
                         yerr=(yerr_lo[~m], yerr_hi[~m]), ls="", color=cmap(i))
            plt.errorbar(x[m], yul[m], xerr=xerr0,
                         yerr=yul[m] * 0.2, uplims=True, ls="", color=cmap(i))

            if not(fit):
                plt.plot(m_engs*to_TeV, fermi_model['dnde'] * e2, color=cmap(i))
                plt.fill_between(m_engs*to_TeV, fermi_model['dnde_lo'] * e2, fermi_model['dnde_hi'] * e2,
                alpha=0.2, color="k")

            plt.xlim(5e-5, 30)
            i+=1

        plt.xscale("log")
        plt.yscale("log")
        plt.legend(fontsize=13)
        plt.grid(which="major", ls="-")
        plt.grid(which="minor", ls=":")
        plt.xlabel("Energy [TeV]", fontsize=13)
        plt.ylabel(r"Energy flux [erg/cm$^2$/s]", fontsize=13)

    def analysis(self, **kwargs):
        
        energy_bins = kwargs.get("energy_bins", np.geomspace(0.0001, 10, 20) * u.TeV)

        fpe = FluxPointsEstimator(
            energy_edges=energy_bins, 
            source=self.target_name, selection_optional="all", **kwargs
            )

        self.flux_points = fpe.run(self.datasets)


        self._flux_points_dataset = FluxPointsDataset(
            data=self.flux_points, models=self.datasets.models
        )
        
        
    @property
    def target_model(self):
        return joint.datasets.models[0].spectral_model
    
    @property
    def verbosity(self):
        return self._verbosity
    
    @property
    def print_datasets(self):
        return self._logging.info(self.datasets)

    @property
    def print_models(self):
        return self._logging.info(joint.datasets.models)
    
    @property
    def target_id(self):
        return self.fermi.target_id

    @property
    def target_name(self):
        return self.veritas.target_name
    
    def define_model(self, model):
        prevmodel = self.datasets.models[self.target_id].spectral_model.tag[0]
        if type(model) == str:
            if model.lower() == "powerlaw":
                model = gammapy_model.PowerLawSpectralModel()
            elif model.lower() == "logparabola":
                model = gammapy_model.LogParabolaSpectralModel()
            else:
                self._logging.error("The input model is not supported yet.")
        elif hasattr(model, "tag"):
            self._logging.error(f"A model, {model.tag[0]}, is imported")
        
        self.datasets.models[self.target_id].spectral_model = model
        newmodel = self.datasets.models[self.target_id].spectral_model.tag[0]
        self._logging.info(f"The spectral model for the target is chaged: {prevmodel}->{newmodel}.")