import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.semanticweb.HermiT.ReasonerFactory;
import org.semanticweb.owlapi.apibinding.OWLManager;
import org.semanticweb.owlapi.model.IRI;
import org.semanticweb.owlapi.model.OWLClass;
import org.semanticweb.owlapi.model.OWLOntology;
import org.semanticweb.owlapi.model.OWLOntologyManager;
import org.semanticweb.owlapi.reasoner.Node;
import org.semanticweb.owlapi.reasoner.OWLReasoner;

public class RunHermitConsistency {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: RunHermitConsistency <ontology.owl>");
            System.exit(2);
        }
        File ontologyFile = new File(args[0]);
        OWLOntologyManager manager = OWLManager.createOWLOntologyManager();
        OWLOntology ontology = manager.loadOntologyFromOntologyDocument(ontologyFile);
        OWLReasoner reasoner = new ReasonerFactory().createReasoner(ontology);
        boolean consistent = reasoner.isConsistent();
        Node<OWLClass> unsatNode = reasoner.getUnsatisfiableClasses();
        List<String> unsatisfiable = new ArrayList<>();
        for (OWLClass cls : unsatNode.getEntitiesMinusBottom()) {
            IRI iri = cls.getIRI();
            unsatisfiable.add(iri.toString());
        }
        Collections.sort(unsatisfiable);
        System.out.println("consistent=" + consistent);
        System.out.println("unsatisfiable_count=" + unsatisfiable.size());
        for (String value : unsatisfiable) {
            System.out.println("unsatisfiable=" + value);
        }
        reasoner.dispose();
        if (!consistent || !unsatisfiable.isEmpty()) {
            System.exit(1);
        }
    }
}
