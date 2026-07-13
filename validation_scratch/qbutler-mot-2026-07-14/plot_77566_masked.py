import json,glob,os,numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
D=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(sorted(glob.glob(D+'/data/live_datasets_*.json'))[-1]))
v=lambda k: d[k][1]
x=np.array(v('ndscan.rid_77566.points.axis_0'),float)/1e6
exc=np.array(v('ndscan.rid_77566.points.channel_excitation_fraction'),float)
an=np.array(v('ndscan.rid_77566.points.channel_atom_number'),float)
gnd=np.array(v('ndscan.rid_77566.points.channel_amp_0_ground'),float)
exd=np.array(v('ndscan.rid_77566.points.channel_amp_0_excited'),float)
# real-atom mask: require meaningful total atom number
for thr in (20000,40000,60000):
    m=an>thr
    print(f"thr={thr}: {m.sum()} shots, exc median={np.median(exc[m]):.4f} range[{exc[m].min():.3f},{exc[m].max():.3f}]")
m=an>40000
fig,ax=plt.subplots(3,1,figsize=(9,10),sharex=True)
ax[0].scatter(x[m],exc[m],s=18,alpha=0.6,color='#1f77b4')
# binned
nb=30;bins=np.linspace(x.min(),x.max(),nb+1);idx=np.digitize(x,bins)
bx,by=[],[]
for b in range(1,nb+1):
    mm=(idx==b)&m
    if mm.sum()>=2: bx.append(x[mm].mean());by.append(np.median(exc[mm]))
ax[0].plot(bx,by,'-o',color='#d62728',ms=4,label='binned median')
ax[0].set_ylim(-0.1,1.0);ax[0].set_ylabel('excitation_fraction\n(atom_number>40k only)')
ax[0].legend(fontsize=8);ax[0].grid(alpha=0.3)
ax[0].set_title("RID 77566 (Charles's REFINING clock line, read-only) — masked to real-atom shots\ncompleted=False N=775",fontsize=10)
ax[1].scatter(x,an,s=10,alpha=0.4,color='#2ca02c');ax[1].axhline(40000,color='k',ls='--',lw=0.7,label='40k mask')
ax[1].set_ylabel('atom_number (all)');ax[1].legend(fontsize=8);ax[1].grid(alpha=0.3)
ax[2].scatter(x[m],gnd[m],s=10,alpha=0.5,label='ground amp',color='#9467bd')
ax[2].scatter(x[m],exd[m],s=10,alpha=0.5,label='excited amp',color='#ff7f0e')
ax[2].set_ylabel('gauss amp (real-atom)');ax[2].legend(fontsize=8);ax[2].grid(alpha=0.3)
ax[2].set_xlabel('frequency_clock_delivery [MHz]')
fig.tight_layout();fig.savefig(D+'/plots/rid77566_masked.png',dpi=110);print('wrote',D+'/plots/rid77566_masked.png')
