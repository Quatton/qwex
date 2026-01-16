package connect

import (
	"context"
	"log"
)

func (s *Service) SyncOnce(ctx context.Context) error {
	remoteHash, err := s.GetRemoteHead(ctx)
	if err != nil {
		log.Fatalf("Error getting remote HEAD: %v\n", err)
		return err
	}

	bundleFile, targetHash, err := s.CreateGitBundle(remoteHash)
	if err != nil {
		log.Fatalf("Error creating git bundle: %v\n", err)
		return err
	}

	err = s.SendBundle(ctx, bundleFile, targetHash)
	if err != nil {
		log.Fatalf("Error sending git bundle: %v\n", err)
		return err
	}

	return nil
}
